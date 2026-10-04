import { useEffect, useState, type RefObject } from 'react';
import { useDocumentVisible } from './polling';

export function useAnimationActivity(ref: RefObject<Element>) {
  const visible = useDocumentVisible();
  const [inView, setInView] = useState(true);
  const [reducedMotion, setReducedMotion] = useState(
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
  );

  useEffect(() => {
    const media = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    const onChange = () => setReducedMotion(media?.matches ?? false);
    media?.addEventListener('change', onChange);
    const element = ref.current;
    const observer = element && typeof IntersectionObserver !== 'undefined'
      ? new IntersectionObserver(([entry]) => setInView(entry?.isIntersecting ?? false))
      : null;
    if (element) observer?.observe(element);
    return () => {
      media?.removeEventListener('change', onChange);
      observer?.disconnect();
    };
  }, [ref]);

  return { visible: visible && inView, reducedMotion, animate: visible && inView && !reducedMotion };
}
