import React, { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { SelectControl } from './SelectControl.jsx';
import { t } from '../i18n.js';

export function DockerFields({ value, onChange, readOnly, api, containerName }) {
  const [containers, setContainers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (readOnly) return;
    let current = true;
    setLoading(true); setError('');
    api('/docker/containers').then(data => { if (current) setContainers(data.containers); }).catch(e => { if (current) setError(e.message); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [api, readOnly, revision]);
  const shortId = value && value.length > 12 ? value.slice(0, 12) : value;
  const readOnlyLabel = containerName ? `${containerName}${shortId ? ` (${shortId})` : ''}` : value;
  return <div className="docker-fields">
    <label>{t('도커 컨테이너')}{readOnly ? <input readOnly value={readOnlyLabel} /> : <div className="compact-input-row"><SelectControl required aria-label={t('도커 컨테이너')} disabled={loading} value={value} onChange={e => {
      const nextId = e.target.value;
      const selected = containers.find(c => c.id === nextId);
      onChange(nextId, selected);
    }}>
      <option value="">{loading ? t('컨테이너 불러오는 중…') : t('컨테이너 선택')}</option>
      {value && !containers.some(c => c.id === value) && <option value={value}>{value}</option>}
      {containers.map(c => <option value={c.id} key={c.id}>{c.name} | {c.image} | {c.status}</option>)}
    </SelectControl><button type="button" className="secondary" disabled={loading} aria-label={t('컨테이너 새로고침')} onClick={() => setRevision(v => v + 1)}><RefreshCw size={15} className={loading ? 'spin' : ''} /></button></div>}</label>
    {error && <p role="alert" className="inline-error">{error}</p>}
    {!readOnly && !loading && !error && !containers.length && <p className="optional">{t('Docker에서 컨테이너를 만든 뒤 새로고침해 주세요.')}</p>}
  </div>;
}
