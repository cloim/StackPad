import { Capacitor, registerPlugin } from '@capacitor/core';

// Android 앱은 화면 파일을 APK에서 열고 API만 PC의 외부 주소로 보낸다. CapacitorHttp가 fetch를 네이티브 요청으로 바꾸므로
// 교차 출처 제약 없이 로그인 쿠키를 함께 보낼 수 있다. 외부 주소는 QR 페어링으로 받아 기기에 저장한다.
export const isNative = Capacitor.isNativePlatform();
const WidgetBridge = isNative ? registerPlugin('WidgetBridge') : null;
let server = '';

// 에뮬레이터 검증용 빌드(VITE_ANDROID_TEST=1)만 adb reverse로 연결한 http://localhost 엔진과 페어링할 수 있다.
const TEST_BUILD = import.meta.env.VITE_ANDROID_TEST === '1';

export async function loadServer() {
  if (!isNative) return;
  server = (await WidgetBridge.server()).url || '';
}

export function serverOrigin() {
  return server;
}

export function nativeHeaders() {
  // 엔진은 변경 요청의 Origin을 확인한다. 네이티브 요청은 Origin을 실을 수 없어 앱 식별 헤더로 대신한다.
  return isNative ? { 'X-StackPad-Client': 'android' } : {};
}

// QR 코드에는 stackpad://pair?server=<외부 주소>&code=<1회용 코드>가 들어 있다.
export function parsePairingLink(link) {
  let url;
  try { url = new URL(link.trim()); } catch { return null; }
  const address = url.searchParams.get('server') || '';
  const code = url.searchParams.get('code') || '';
  const allowed = /^https:\/\/[^/?#]+$/.test(address) || (TEST_BUILD && /^http:\/\/localhost:\d+$/.test(address));
  if (url.protocol !== 'stackpad:' || !code || !allowed) return null;
  return { server: address, code };
}

export async function scanPairingCode() {
  const { CapacitorBarcodeScanner, CapacitorBarcodeScannerTypeHint } = await import('@capacitor/barcode-scanner');
  const result = await CapacitorBarcodeScanner.scanBarcode({ hint: CapacitorBarcodeScannerTypeHint.QR_CODE });
  return result.ScanResult || '';
}

export async function pair(api, link) {
  const parsed = parsePairingLink(link);
  if (!parsed) throw new Error('INVALID_LINK');
  const previous = server;
  server = parsed.server;
  try {
    const { device } = await WidgetBridge.status();
    await api('/pairing/claim', { method: 'POST', body: JSON.stringify({ code: parsed.code, name: device || 'Android' }) });
    await WidgetBridge.saveServer({ url: parsed.server });
  } catch (error) {
    server = previous;
    throw error;
  }
}

export async function forgetServer() {
  if (!isNative) return;
  server = '';
  await WidgetBridge.clearServer();
}

// 홈 화면 위젯은 사용량만 읽는 기기 토큰으로 엔진에 접속한다. 해제되었거나 없으면 새로 발급해 네이티브 저장소에 둔다.
export async function connectWidget(api) {
  if (!isNative) return;
  const state = await WidgetBridge.status();
  if (state.id) {
    const { devices } = await api('/widget/tokens');
    if (devices.some(device => device.id === state.id)) return;
  }
  const issued = await api('/widget/tokens', { method: 'POST', body: JSON.stringify({ name: state.device || 'Android' }) });
  await WidgetBridge.saveToken({ id: issued.id, token: issued.token, origin: server });
}

export async function pinWidget() {
  await WidgetBridge.pinWidget();
}

// 로그아웃하면 이 기기의 위젯 연결도 엔진에서 해제한다. 엔진에 닿지 않아도 기기 저장값은 지운다.
export async function disconnectWidget(api) {
  if (!isNative) return;
  const { id } = await WidgetBridge.status();
  if (id) await api(`/widget/tokens/${id}`, { method: 'DELETE' }).catch(() => {});
  await WidgetBridge.clearToken();
}

// 앱 화면이 받은 사용량을 위젯에도 넘겨, 위젯이 앱보다 오래된 값을 보이지 않게 한다.
export function shareUsage(data) {
  if (!isNative) return;
  WidgetBridge.saveUsage({ usage: JSON.stringify(data) }).catch(() => {});
}
