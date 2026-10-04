import { useEffect, useState } from 'react';
import type { TabType } from '../components/Header';

const TABS: TabType[] = ['overview', 'factcheck', 'fullgraph', 'timeline', 'masala', 'graph', 'vector', 'cache', 'corpus', 'eval'];

function currentTab(): TabType {
  const tab = window.location.hash.match(/^#\/dashboard\/([a-z]+)$/)?.[1] as TabType | undefined;
  return tab && TABS.includes(tab) ? tab : 'overview';
}

export function useDashboardTab(): [TabType, (tab: TabType) => void] {
  const [tab, setTab] = useState<TabType>(currentTab);
  useEffect(() => {
    const sync = () => setTab(currentTab());
    window.addEventListener('hashchange', sync);
    window.addEventListener('popstate', sync);
    return () => {
      window.removeEventListener('hashchange', sync);
      window.removeEventListener('popstate', sync);
    };
  }, []);
  return [tab, (next) => {
    if (window.location.hash !== `#/dashboard/${next}`) window.location.hash = `#/dashboard/${next}`;
    setTab(next);
  }];
}
