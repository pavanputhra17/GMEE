// Static JSON override for Render hosting without a backend
let staticDataPromise: Promise<any> | null = null;
const loadStaticData = () => {
  if (!staticDataPromise) {
    staticDataPromise = fetch('/data.json').then(res => res.json()).catch(err => {
      console.error('Failed to load static data', err);
      return { articles: [], domains: [], nlp_counts: {} };
    });
  }
  return staticDataPromise;
};

export const apiClient = {
  get: async <T = unknown>(endpoint: string, options?: unknown): Promise<T> => {
    const data = await loadStaticData();
    const url = new URL(endpoint, 'http://localhost');
    const path = url.pathname;
    const searchParams = url.searchParams;

    if (path === '/health/ready') {
      return { status: 'ok', postgres: 'ok', neo4j: 'ok', redis: 'ok' } as any;
    }

    if (path === '/dashboard') {
      return {
        generated_at: new Date().toISOString(),
        services: { postgres: 'ok', neo4j: 'ok', redis: 'ok' },
        articles_total: data.articles.length,
        nlp_status_counts: data.nlp_counts,
        claims_total: data.articles.length * 2,
        embedded_claims: data.articles.length,
        entities_total: data.articles.length * 3,
        last_evolution_run: { run_at: new Date().toISOString(), claims_in_corpus: data.articles.length },
        graph: {
          available: true,
          nodes: { Article: data.articles.length, Domain: data.domains.length },
          relationships: data.articles.length * 2,
        },
        cache: {
          available: true,
          used_memory_human: '128 MB',
          used_memory_mb: 128,
        }
      } as any;
    }

    if (path === '/corpus/stats') {
      return {
        total: data.articles.length,
        embedded: data.articles.length,
        domains: data.domains.length,
        earliest: data.articles.length > 0 ? data.articles[data.articles.length - 1].published_at : null,
        latest: data.articles.length > 0 ? data.articles[0].published_at : null,
        nlp_counts: data.nlp_counts
      } as any;
    }

    if (path === '/corpus/articles') {
      const q = searchParams.get('q')?.toLowerCase() || '';
      const domain = searchParams.get('domain') || '';
      const limit = parseInt(searchParams.get('limit') || '30', 10);
      const offset = parseInt(searchParams.get('offset') || '0', 10);

      let filtered = data.articles;
      if (q) filtered = filtered.filter((a: any) => (a.title && a.title.toLowerCase().includes(q)) || (a.author && a.author.toLowerCase().includes(q)));
      if (domain) filtered = filtered.filter((a: any) => a.domain === domain);

      return {
        total: filtered.length,
        limit,
        offset,
        items: filtered.slice(offset, offset + limit),
        domains: data.domains
      } as any;
    }

    if (path === '/corpus/articles/recent') {
      const limit = parseInt(searchParams.get('limit') || '12', 10);
      return {
        items: data.articles.slice(0, limit)
      } as any;
    }

    if (path === '/corpus/search') {
      const q = searchParams.get('q')?.toLowerCase() || '';
      const limit = parseInt(searchParams.get('limit') || '10', 10);
      let filtered = data.articles;
      if (q) filtered = filtered.filter((a: any) => (a.title && a.title.toLowerCase().includes(q)));
      const items = filtered.slice(0, limit).map((a: any, idx: number) => ({ ...a, score: 0.99 - (idx * 0.01) }));
      return {
        query: q,
        count: items.length,
        items
      } as any;
    }

    if (path === '/corpus/graph/story-clusters') {
      return { clusters: [] } as any;
    }

    if (path === '/graph/full' || path === '/graph/claims') {
      const sample = data.articles.slice(0, 50);
      const nodes = sample.map((a: any, i: number) => ({
        id: a.id,
        title: a.title,
        domain: a.domain,
        url: a.url,
        article_id: a.id,
        published_at: a.published_at,
        deg: Math.floor(Math.random() * 5),
        verdict: Math.random() > 0.8 ? 'FALSE' : (Math.random() > 0.5 ? 'MISLEADING' : 'UNVERIFIED'),
        prob: Math.random() * 0.9 + 0.1,
      }));
      const edges = [];
      for (let i = 0; i < nodes.length - 1; i++) {
        if (Math.random() > 0.3) {
          edges.push({ src: nodes[i].id, dst: nodes[i + 1].id, score: Math.random() * 0.5 + 0.5 });
        }
      }
      return { nodes, edges, counts: { nodes: nodes.length, edges: edges.length } } as any;
    }

    if (path === '/graph/timeline') {
      const limit = parseInt(searchParams.get('limit') || '60', 10);
      const sample = data.articles.slice(0, limit);
      const clusters = sample.map((a: any) => ({
        id: a.id,
        title: a.title,
        domain: a.domain,
        url: a.url,
        published_at: a.published_at,
        newest_member_at: a.published_at,
        deg: 0,
        members: []
      }));
      return { clusters, count: clusters.length, focused: !!searchParams.get('article_id') } as any;
    }

    // Default empty response
    return {} as any;
  },
  post: async <T = unknown>(endpoint: string, body: unknown, options?: unknown): Promise<T> => {
    // Mock POST endpoints
    return { status: 'mock_success' } as any;
  },
  download: async (endpoint: string, options?: unknown) => {
      return { blob: new Blob(), filename: 'download.txt' };
  }
};
};
