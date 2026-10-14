import React, { useEffect, useState } from 'react';
import { Container, LoaderCircle, Monitor, PlugZap, Server, WandSparkles } from 'lucide-react';
import { t } from '../i18n.js';

export const emptyRemote = { host: '', start: '', stop: '', status: '', logs: '', health_url: '' };
const unitPattern = /^[A-Za-z0-9@._:-]+$/;
// One SSH config read per page load is enough for every open form.
let hostList = null;

export function KindSwitch({ kind, onChange, disabled, local, docker = true }) {
  return <div className="kind-switch" role="radiogroup" aria-label={t('실행 위치')}>
    <button type="button" role="radio" aria-checked={kind === 'local'} disabled={disabled} onClick={() => onChange('local')}><Monitor size={13} aria-hidden="true" />{t('로컬')}</button>
    <button type="button" role="radio" aria-checked={kind === 'remote'} disabled={disabled || (!local && kind !== 'remote')} title={local ? undefined : t('원격 서버는 이 PC에서 접속해 등록할 수 있어요.')} onClick={() => onChange('remote')}><Server size={13} />{t('원격 서버')}</button>
    {(docker || kind === 'docker') && <button type="button" role="radio" aria-checked={kind === 'docker'} disabled={disabled} onClick={() => onChange('docker')}><Container size={13} aria-hidden="true" />{t('도커')}</button>}
  </div>;
}

export function RemoteFields({ value, onChange, readOnly, api }) {
  const [hosts, setHosts] = useState([]);
  const [unit, setUnit] = useState('');
  const [test, setTest] = useState(null);
  const listId = `remote-hosts-${React.useId().replace(/:/g, '')}`;
  useEffect(() => {
    if (readOnly) return;
    let active = true;
    hostList ||= api('/remote/hosts').then(data => data.hosts).catch(() => { hostList = null; return []; });
    hostList.then(list => { if (active) setHosts(list); });
    return () => { active = false; };
  }, [api, readOnly]);
  const set = (key, next) => { if (!readOnly) onChange({ ...value, [key]: next }); };
  function fill() {
    const name = unit.trim();
    onChange({ ...value, start: `sudo systemctl start ${name}`, stop: `sudo systemctl stop ${name}`, status: `systemctl is-active --quiet ${name}`, logs: `journalctl -u ${name} -n 300 --no-pager` });
  }
  async function check() {
    setTest({ pending: true });
    try { setTest(await api('/remote/test', { method: 'POST', body: JSON.stringify({ host: value.host }) })); }
    catch (error) { setTest({ ok: false, message: error.message }); }
  }
  return <div className="remote-fields">
    <label>{t('호스트')}<div className="remote-host">
      <input aria-label={t('호스트')} required readOnly={readOnly} list={listId} maxLength={255} value={value.host} onChange={e => { set('host', e.target.value); setTest(null); }} placeholder={t('SSH 설정 별칭 또는 user@host:22')} />
      {!readOnly && <button type="button" className="secondary" disabled={!value.host.trim() || test?.pending} onClick={check}>{test?.pending ? <LoaderCircle size={15} className="spin" /> : <PlugZap size={15} />}{t('접속 테스트')}</button>}
    </div>
      <datalist id={listId}>{hosts.map(host => <option key={host} value={host} />)}</datalist>
      {test && !test.pending && <small role="status" className={test.ok ? 'remote-ok' : 'remote-fail'}>{test.message}</small>}
    </label>
    {!readOnly && <label><span>{t('systemd 서비스 이름')} <span className="optional">{t('입력하면 아래 명령을 채워 드려요')}</span></span><div className="remote-host">
      <input aria-label={t('systemd 서비스 이름')} value={unit} maxLength={200} onChange={e => setUnit(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); if (unitPattern.test(unit.trim())) fill(); } }} placeholder={t('예: order-api')} />
      <button type="button" className="secondary" disabled={!unitPattern.test(unit.trim())} onClick={fill}><WandSparkles size={15} />{t('명령 채우기')}</button>
    </div></label>}
    <div className="remote-row">
      <label>{t('시작 명령')}<input required readOnly={readOnly} maxLength={2000} aria-label={t('시작 명령')} value={value.start} onChange={e => set('start', e.target.value)} placeholder="sudo systemctl start order-api" /></label>
      <label>{t('종료 명령')}<input required readOnly={readOnly} maxLength={2000} aria-label={t('종료 명령')} value={value.stop} onChange={e => set('stop', e.target.value)} placeholder="sudo systemctl stop order-api" /></label>
    </div>
    <div className="remote-row">
      <label>{t('상태 명령')}<input required readOnly={readOnly} maxLength={2000} aria-label={t('상태 명령')} value={value.status} onChange={e => set('status', e.target.value)} placeholder="systemctl is-active --quiet order-api" />{!readOnly && <small>{t('종료 코드 0이면 실행 중으로 표시합니다.')}</small>}</label>
      <label><span>{t('로그 명령')} <span className="optional">{t('선택')}</span></span><input readOnly={readOnly} maxLength={2000} aria-label={t('로그 명령')} value={value.logs} onChange={e => set('logs', e.target.value)} placeholder="journalctl -u order-api -n 300 --no-pager" /></label>
    </div>
    <label><span>{t('상태 확인 URL')} <span className="optional">{t('선택')}</span></span><input type="url" readOnly={readOnly} maxLength={1000} aria-label={t('상태 확인 URL')} value={value.health_url} onChange={e => set('health_url', e.target.value)} placeholder="http://10.0.0.5:8000/health" />{!readOnly && <small>{t('사설망 주소나 등록한 호스트 주소를 사용할 수 있고, 응답하면 상태 명령 대신 실행 중으로 봅니다.')}</small>}</label>
    {!readOnly && <p className="optional remote-guide">{t('SSH 키 인증으로 접속하며 비밀번호는 저장하지 않습니다. 처음 접속하는 호스트는 터미널에서 ssh로 한 번 접속해 호스트 키를 등록해 주세요. sudo가 필요한 명령은 원격 서버의 sudoers에서 비밀번호 없이 허용해 주세요.')}</p>}
  </div>;
}
