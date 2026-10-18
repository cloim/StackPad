import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import Ansi from 'ansi-to-react';
import { ArrowDown, ArrowUp, Check, ChevronDown, ChevronUp, Filter, Search, Terminal, X } from 'lucide-react';
import { t } from '../i18n.js';

const ANSI_REGEX = /[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g;
const ERROR_REGEX = /(error|fatal|exception|traceback|panic|failed|uncaught|syntaxerror)/i;
const LINE_HEIGHT = 20;

export function stripAnsi(text) {
  return (text || '').replace(ANSI_REGEX, '');
}

export function isErrorLine(plainText) {
  return ERROR_REGEX.test(plainText);
}

export function LogViewer({ rawLogs, serviceName, loading, targetErrorLine }) {
  const [search, setSearch] = useState('');
  const [onlyErrors, setOnlyErrors] = useState(false);
  const [activeMatch, setActiveMatch] = useState(0);
  const [scrollTop, setScrollTop] = useState(0);
  const [containerHeight, setContainerHeight] = useState(400);

  const containerRef = useRef(null);
  const followRef = useRef(true);

  // ResizeObserver for dynamic container height
  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        setContainerHeight(entry.contentRect.height);
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  // Split lines and parse metadata
  const lines = useMemo(() => {
    if (!rawLogs) return [];
    return rawLogs.split('\n');
  }, [rawLogs]);

  const parsedLines = useMemo(() => {
    return lines.map((raw, idx) => {
      const plain = stripAnsi(raw);
      const isErr = isErrorLine(plain);
      return { id: idx, raw, plain, isErr };
    });
  }, [lines]);

  // Filter lines by "onlyErrors" and "search"
  const filteredLines = useMemo(() => {
    let result = parsedLines;
    if (onlyErrors) {
      result = result.filter(line => line.isErr);
    }
    return result;
  }, [parsedLines, onlyErrors]);

  // Search match positions in filteredLines
  const matches = useMemo(() => {
    if (!search.trim()) return [];
    const query = search.toLowerCase();
    const result = [];
    filteredLines.forEach((item, fIdx) => {
      if (item.plain.toLowerCase().includes(query)) {
        result.push(fIdx);
      }
    });
    return result;
  }, [filteredLines, search]);

  // When search changes, reset activeMatch and pause follow
  useEffect(() => {
    if (search.trim()) {
      followRef.current = false;
      setActiveMatch(0);
      if (matches.length > 0 && containerRef.current) {
        scrollToFilteredIndex(matches[0]);
      }
    } else {
      followRef.current = true;
    }
  }, [search]);

  // If targetErrorLine is provided, find and scroll to it
  useEffect(() => {
    if (!targetErrorLine || !parsedLines.length) return;
    const cleanTarget = stripAnsi(targetErrorLine).trim();
    if (!cleanTarget) return;
    const foundIdx = parsedLines.findIndex(l => l.plain.includes(cleanTarget));
    if (foundIdx !== -1) {
      followRef.current = false;
      if (onlyErrors) setOnlyErrors(false);
      setTimeout(() => {
        if (containerRef.current) {
          containerRef.current.scrollTop = Math.max(0, foundIdx * LINE_HEIGHT - 60);
        }
      }, 50);
    }
  }, [targetErrorLine, parsedLines, onlyErrors]);

  // Follow auto-scroll when new logs arrive and followRef is true
  useLayoutEffect(() => {
    if (followRef.current && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [filteredLines.length]);

  function handleScroll(e) {
    const el = e.currentTarget;
    setScrollTop(el.scrollTop);
    // User scrolled near bottom -> re-enable follow (only if not actively searching)
    const isAtBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 30;
    if (!search.trim()) {
      followRef.current = isAtBottom;
    }
  }

  function scrollToFilteredIndex(fIdx) {
    if (!containerRef.current) return;
    const targetScroll = Math.max(0, fIdx * LINE_HEIGHT - containerHeight / 2 + LINE_HEIGHT / 2);
    containerRef.current.scrollTop = targetScroll;
  }

  function nextMatch() {
    if (!matches.length) return;
    const next = (activeMatch + 1) % matches.length;
    setActiveMatch(next);
    scrollToFilteredIndex(matches[next]);
  }

  function prevMatch() {
    if (!matches.length) return;
    const prev = (activeMatch - 1 + matches.length) % matches.length;
    setActiveMatch(prev);
    scrollToFilteredIndex(matches[prev]);
  }

  // Virtual window calculation
  const totalCount = filteredLines.length;
  const visibleCount = Math.ceil(containerHeight / LINE_HEIGHT);
  const startIndex = Math.max(0, Math.floor(scrollTop / LINE_HEIGHT) - 5);
  const endIndex = Math.min(totalCount, startIndex + visibleCount + 10);
  const visibleLines = filteredLines.slice(startIndex, endIndex);

  const paddingTop = startIndex * LINE_HEIGHT;
  const paddingBottom = Math.max(0, (totalCount - endIndex) * LINE_HEIGHT);

  function highlightSearch(plain, raw) {
    if (!search.trim()) {
      return <Ansi linkify={false}>{raw}</Ansi>;
    }
    const query = search;
    const parts = plain.split(new RegExp(`(${query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')})`, 'gi'));
    return parts.map((part, i) => {
      if (part.toLowerCase() === query.toLowerCase()) {
        return <mark key={i} className="log-search-match">{part}</mark>;
      }
      return <span key={i}>{part}</span>;
    });
  }

  return (
    <section className="log-panel">
      <div className="log-head">
        <div className="panel-title">
          <Terminal size={16} />
          <h2>{t('실행 로그')}</h2>
          {serviceName && <span>{serviceName}</span>}
        </div>

        {/* Search and Error Filter Header */}
        <div className="log-toolbar">
          <div className="log-search-input-wrap">
            <Search size={13} className="search-icon" />
            <input
              type="text"
              aria-label={t('로그 검색')}
              placeholder={t('로그 검색')}
              value={search}
              onChange={e => setSearch(e.target.value)}
            />
            {search && (
              <button
                type="button"
                className="tool-button clear-btn"
                aria-label={t('검색어 지우기')}
                onClick={() => setSearch('')}
              >
                <X size={12} />
              </button>
            )}
          </div>

          {search && (
            <div className="search-nav">
              <span className="search-count">
                {matches.length > 0 ? `${activeMatch + 1}/${matches.length}` : t('0개')}
              </span>
              <button
                type="button"
                className="tool-button"
                disabled={!matches.length}
                onClick={prevMatch}
                aria-label={t('이전 검색 결과')}
              >
                <ChevronUp size={14} />
              </button>
              <button
                type="button"
                className="tool-button"
                disabled={!matches.length}
                onClick={nextMatch}
                aria-label={t('다음 검색 결과')}
              >
                <ChevronDown size={14} />
              </button>
            </div>
          )}

          <button
            type="button"
            className={`filter-btn ${onlyErrors ? 'active' : ''}`}
            onClick={() => setOnlyErrors(!onlyErrors)}
            title={t('오류 줄만 보기')}
            aria-pressed={onlyErrors}
          >
            <Filter size={13} />
            <span>{t('오류만')}</span>
          </button>
        </div>
      </div>

      <div
        ref={containerRef}
        className="log-container"
        onScroll={handleScroll}
        tabIndex={0}
        role="region"
        aria-label={t('로그 본문')}
      >
        {loading ? (
          <p className="log-placeholder">{t('로그를 불러오는 중…')}</p>
        ) : !serviceName ? (
          <p className="log-placeholder">{t('서비스를 선택하면 실행 로그가 여기에 표시됩니다.')}</p>
        ) : !lines.length ? (
          <p className="log-placeholder">{t('아직 기록된 로그가 없습니다. 서비스를 실행하면 여기에 표시됩니다.')}</p>
        ) : (
          <div
            className="log-scroll-content"
            style={{ paddingTop: `${paddingTop}px`, paddingBottom: `${paddingBottom}px` }}
          >
            {visibleLines.map((item, relIdx) => {
              const actualIdx = startIndex + relIdx;
              const isCurrentMatch = matches.length > 0 && matches[activeMatch] === actualIdx;
              return (
                <div
                  key={item.id}
                  className={`log-line ${item.isErr ? 'error-line' : ''} ${isCurrentMatch ? 'current-match' : ''}`}
                  style={{ height: `${LINE_HEIGHT}px` }}
                >
                  <span className="log-line-num">{item.id + 1}</span>
                  <span className="log-line-text">
                    {highlightSearch(item.plain, item.raw)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </section>
  );
}
