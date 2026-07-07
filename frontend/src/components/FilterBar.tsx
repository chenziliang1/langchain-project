import { useState, useEffect, useRef, useCallback } from 'react';
import { Search, MapPin, User, Tag, Sparkles } from 'lucide-react';
import { api } from '../api/client';
import type { FilterState } from '../types';

interface Props {
  filters: FilterState;
  onChange: (filters: FilterState) => void;
  onSearch: () => void;
  loading?: boolean;
}

function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const h = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(h);
  }, [value, delay]);
  return debounced;
}

export default function FilterBar({ filters, onChange, onSearch, loading }: Props) {
  const update = (key: keyof FilterState, value: string) => {
    onChange({ ...filters, [key]: value });
  };

  return (
    <div
      style={{
        display: 'flex',
        gap: 10,
        alignItems: 'center',
        flexWrap: 'wrap',
        background: 'white',
        padding: '10px 14px',
        borderRadius: 10,
        boxShadow: '0 1px 3px rgba(0,0,0,0.06)',
        marginBottom: 12,
      }}
    >
      {/* Date Range */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <input
          type="date"
          value={filters.startDate}
          onChange={(e) => update('startDate', e.target.value)}
          style={inputStyle}
        />
        <span style={{ color: '#999', fontSize: 13 }}>to</span>
        <input
          type="date"
          value={filters.endDate}
          onChange={(e) => update('endDate', e.target.value)}
          style={inputStyle}
        />
      </div>

      {/* Location with Autocomplete */}
      <AutocompleteInput
        icon={<MapPin size={14} color="#666" />}
        placeholder="Region / Location"
        value={filters.location}
        exactValue={filters.locationExact}
        onChange={(val, exact) => {
          onChange({ ...filters, location: val, locationExact: exact || '' });
        }}
        fetchSuggestions={(q) => api.suggestLocations(q)}
      />

      {/* Actor with Autocomplete */}
      <AutocompleteInput
        icon={<User size={14} color="#666" />}
        placeholder="Actor name"
        value={filters.actor}
        exactValue={filters.actorExact}
        onChange={(val, exact) => {
          onChange({ ...filters, actor: val, actorExact: exact || '' });
        }}
        fetchSuggestions={(q) => api.suggestActors(q)}
      />

      {/* Event Type */}
      <div style={fieldWrapStyle}>
        <Tag size={14} color="#666" />
        <select
          value={filters.eventType}
          onChange={(e) => update('eventType', e.target.value)}
          style={{ ...inputStyle, width: 120, cursor: 'pointer' }}
        >
          <option value="any">Any Type</option>
          <option value="conflict">Conflict</option>
          <option value="cooperation">Cooperation</option>
          <option value="protest">Protest</option>
        </select>
      </div>

      {/* Keyword */}
      <div style={{ ...fieldWrapStyle, flex: 1, minWidth: 160 }}>
        <Sparkles size={14} color="#8b5cf6" />
        <input
          type="text"
          placeholder="Search headline, summary, actors..."
          value={filters.keyword}
          onChange={(e) => update('keyword', e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && onSearch()}
          style={{ ...inputStyle, flex: 1, minWidth: 120 }}
        />
      </div>

      {/* Search Button */}
      <button
        onClick={onSearch}
        disabled={loading}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '7px 16px',
          background: loading ? '#c4b5fd' : '#8b5cf6',
          color: 'white',
          border: 'none',
          borderRadius: 8,
          fontSize: 13,
          fontWeight: 600,
          cursor: loading ? 'not-allowed' : 'pointer',
          whiteSpace: 'nowrap',
        }}
      >
        <Search size={14} />
        {loading ? 'Searching...' : 'Search Events'}
      </button>
    </div>
  );
}

/* Autocomplete input component */
function AutocompleteInput({
  icon,
  placeholder,
  value,
  exactValue,
  onChange,
  fetchSuggestions,
}: {
  icon: React.ReactNode;
  placeholder: string;
  value: string;
  exactValue: string;
  onChange: (val: string, exact: string) => void;
  fetchSuggestions: (q: string) => Promise<any>;
}) {
  const [open, setOpen] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [fetching, setFetching] = useState(false);
  const debouncedValue = useDebounce(value, 200);
  const wrapRef = useRef<HTMLDivElement>(null);
  const ignoreBlur = useRef(false);

  const load = useCallback(async (q: string) => {
    if (!q || q.length < 2) {
      setSuggestions([]);
      return;
    }
    setFetching(true);
    try {
      const res = await fetchSuggestions(q);
      if (res.ok) {
        setSuggestions(res.items || []);
      }
    } catch {
      setSuggestions([]);
    } finally {
      setFetching(false);
    }
  }, [fetchSuggestions]);

  useEffect(() => {
    load(debouncedValue);
  }, [debouncedValue, load]);

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const hasExact = exactValue && exactValue.toUpperCase() === value.toUpperCase();

  return (
    <div ref={wrapRef} style={{ ...fieldWrapStyle, position: 'relative' }}>
      {icon}
      <input
        type="text"
        placeholder={placeholder}
        value={value}
        onChange={(e) => {
          onChange(e.target.value, '');
          setOpen(true);
        }}
        onFocus={() => value.length >= 2 && setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false);
        }}
        style={{ ...inputStyle, width: 140 }}
      />
      {hasExact && (
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: '50%',
            background: '#22c55e',
            flexShrink: 0,
          }}
          title="Exact match (fast index search)"
        />
      )}

      {open && suggestions.length > 0 && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            background: 'white',
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            zIndex: 100,
            maxHeight: 220,
            overflow: 'auto',
          }}
        >
          {suggestions.map((item, i) => (
            <div
              key={i}
              onMouseDown={(e) => {
                e.preventDefault();
                ignoreBlur.current = true;
              }}
              onClick={() => {
                onChange(item, item);
                setOpen(false);
              }}
              style={{
                padding: '8px 12px',
                fontSize: 13,
                cursor: 'pointer',
                borderBottom: i < suggestions.length - 1 ? '1px solid #f3f4f6' : 'none',
                color: '#374151',
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = '#f9fafb';
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLDivElement).style.background = 'white';
              }}
            >
              {item}
            </div>
          ))}
        </div>
      )}
      {open && fetching && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            padding: '8px 12px',
            fontSize: 12,
            color: '#9ca3af',
            background: 'white',
            border: '1px solid #e5e7eb',
            borderRadius: 8,
            zIndex: 100,
          }}
        >
          Loading...
        </div>
      )}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  border: '1px solid #e5e7eb',
  borderRadius: 6,
  padding: '6px 10px',
  fontSize: 13,
  outline: 'none',
  color: '#374151',
};

const fieldWrapStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 6,
  background: '#f9fafb',
  padding: '4px 8px',
  borderRadius: 6,
  border: '1px solid #e5e7eb',
};
