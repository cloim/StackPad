// Korean source text is the message key; English comes from the dictionary and falls back to the key.
import en from './locales/en.js';

const STORAGE_KEY = 'stackpad-lang';
export const LOCALES = [{ id: 'ko', name: '한국어' }, { id: 'en', name: 'English' }];

function detect() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (LOCALES.some(item => item.id === saved)) return saved;
  } catch { /* 저장소를 못 쓰면 브라우저 언어를 따른다. */ }
  return (navigator.languages?.[0] || navigator.language || 'en').toLowerCase().startsWith('ko') ? 'ko' : 'en';
}

export const locale = detect();
document.documentElement.lang = locale;

// t('{0}개 실행 중', count) fills numbered placeholders in either language.
export function t(text, ...args) {
  const template = locale === 'en' ? en[text] ?? text : text;
  return args.length ? template.replace(/\{(\d+)\}/g, (match, index) => String(args[index] ?? '')) : template;
}

export function setLocale(next) {
  try { localStorage.setItem(STORAGE_KEY, next); } catch { /* 이번 화면에만 적용된다. */ }
  window.location.reload();
}
