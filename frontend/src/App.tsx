import { useEffect, useState } from 'react';
import { SystemHealth } from './pages/SystemHealth';
import { Landing } from './pages/Landing';

type Route = 'landing' | 'dashboard';

function currentRoute(): Route {
  return typeof window !== 'undefined' &&
    window.location.hash.startsWith('#/dashboard')
    ? 'dashboard'
    : 'landing';
}

function App() {
  const [route, setRoute] = useState<Route>(currentRoute);

  useEffect(() => {
    const onHash = () => setRoute(currentRoute());
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  return (
    <div className="App">
      {route === 'dashboard' ? <SystemHealth /> : <Landing />}
    </div>
  );
}

export default App;
