import { useEffect, useRef } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { GeoPoint, GeoEventPoint } from '../types';

interface Props {
  data?: GeoPoint[];
  eventPoints?: GeoEventPoint[];
  title?: string;
  selectedEventId?: number | null;
  onEventSelect?: (event: GeoEventPoint) => void;
}

export default function MapPanel({
  data,
  eventPoints,
  title = 'Event Density Map',
  selectedEventId,
  onEventSelect,
}: Props) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<L.Map | null>(null);
  const layerGroup = useRef<L.LayerGroup | null>(null);
  const markerMap = useRef<Record<number, L.CircleMarker>>({});

  // Initialize map
  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    const map = L.map(mapRef.current).setView([40, -95], 4);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© OpenStreetMap',
      maxZoom: 18,
    }).addTo(map);

    mapInstance.current = map;
    layerGroup.current = L.layerGroup().addTo(map);

    // Fix: invalidate size when container becomes visible (e.g. tab switch)
    const observer = new ResizeObserver(() => {
      mapInstance.current?.invalidateSize();
    });
    observer.observe(mapRef.current);

    return () => {
      observer.disconnect();
      mapInstance.current?.remove();
      mapInstance.current = null;
      layerGroup.current = null;
      markerMap.current = {};
    };
  }, []);

  // Render markers when data changes
  useEffect(() => {
    if (!mapInstance.current || !layerGroup.current) return;

    layerGroup.current.clearLayers();
    markerMap.current = {};

    const bounds: L.LatLngExpression[] = [];

    // Mode 1: Event points (from filtered search)
    if (eventPoints && eventPoints.length > 0) {
      eventPoints.forEach((point) => {
        if (point.lat == null || point.lng == null) return;
        bounds.push([point.lat, point.lng]);

        const isSelected = selectedEventId === point.GlobalEventID;
        const color = getEventColor(point.GoldsteinScale, point.event_type_label);
        const radius = isSelected ? 10 : 7;
        const fillOpacity = isSelected ? 1 : 0.85;

        const circle = L.circleMarker([point.lat, point.lng], {
          radius,
          fillColor: color,
          color: isSelected ? '#7c3aed' : '#fff',
          weight: isSelected ? 3 : 1,
          opacity: 1,
          fillOpacity,
        });

        const popupHtml = `
          <div style="font-size:12px;min-width:180px">
            <strong style="font-size:13px;color:#1f2937">${escapeHtml(point.headline || `${point.Actor1Name || 'Unknown'} vs ${point.Actor2Name || 'Unknown'}`)}</strong><br/>
            <div style="margin-top:4px;color:#6b7280">
              ${point.SQLDATE}<br/>
              ${point.ActionGeo_FullName ? escapeHtml(point.ActionGeo_FullName) + '<br/>' : ''}
              ${point.Actor1Name ? 'Actor: ' + escapeHtml(point.Actor1Name) + '<br/>' : ''}
              ${point.GoldsteinScale !== undefined && point.GoldsteinScale !== null ? `Goldstein: ${point.GoldsteinScale.toFixed(1)}<br/>` : ''}
              ${point.NumArticles ? `Articles: ${point.NumArticles.toLocaleString()}<br/>` : ''}
            </div>
          </div>
        `;
        circle.bindPopup(popupHtml);

        circle.on('click', () => {
          if (onEventSelect) {
            onEventSelect(point);
          }
        });

        circle.addTo(layerGroup.current!);
        markerMap.current[point.GlobalEventID] = circle;
      });
    }
    // Mode 2: Heatmap grid points
    else if (data && data.length > 0) {
      data.forEach((point) => {
        bounds.push([point.lat, point.lng]);

        const color = point.avg_conflict !== undefined
          ? point.avg_conflict < -5 ? '#dc2626'
          : point.avg_conflict < 0 ? '#f97316'
          : '#3b82f6'
          : '#6b7280';

        const radius = Math.max(4, Math.min(20, Math.sqrt(point.intensity) * 2));

        const circle = L.circleMarker([point.lat, point.lng], {
          radius,
          fillColor: color,
          color: '#fff',
          weight: 1,
          opacity: 1,
          fillOpacity: 0.7,
        });

        circle.bindPopup(`
          <div style="font-size:12px">
            <strong>${escapeHtml(point.sample_location || 'Unknown')}</strong><br/>
            Intensity: ${point.intensity}<br/>
            Avg Conflict: ${point.avg_conflict?.toFixed(2) ?? 'N/A'}
          </div>
        `);

        circle.addTo(layerGroup.current!);
      });
    }

    if (bounds.length > 0) {
      mapInstance.current.fitBounds(bounds as L.LatLngBoundsExpression, { padding: [40, 40] });
    }
  }, [data, eventPoints, selectedEventId, onEventSelect]);

  // Fly to selected event
  useEffect(() => {
    if (selectedEventId && mapInstance.current) {
      const point = eventPoints?.find(p => p.GlobalEventID === selectedEventId);
      if (point && point.lat != null && point.lng != null) {
        mapInstance.current.flyTo([point.lat, point.lng], 10, {
          duration: 1.2,
        });
        // Open popup for the selected marker
        const marker = markerMap.current[selectedEventId];
        if (marker) {
          marker.openPopup();
        }
      }
    }
  }, [selectedEventId, eventPoints]);

  return (
    <div className="panel">
      <h3>{title}</h3>
      <div ref={mapRef} style={{ width: '100%', height: 400, borderRadius: 8 }} />
      <div className="map-legend">
        <span style={{ fontWeight: 600, color: '#374151' }}>Legend:</span>
        <div className="map-legend-item">
          <div className="map-legend-dot" style={{ background: '#dc2626' }} />
          <span>Conflict</span>
        </div>
        <div className="map-legend-item">
          <div className="map-legend-dot" style={{ background: '#16a34a' }} />
          <span>Cooperation</span>
        </div>
        <div className="map-legend-item">
          <div className="map-legend-dot" style={{ background: '#f59e0b' }} />
          <span>Protest</span>
        </div>
        <div className="map-legend-item">
          <div className="map-legend-dot" style={{ background: '#3b82f6' }} />
          <span>Other</span>
        </div>
      </div>
    </div>
  );
}

function getEventColor(goldstein?: number, eventTypeLabel?: string): string {
  if (eventTypeLabel?.toLowerCase().includes('conflict') || (goldstein !== undefined && goldstein < -5)) {
    return '#dc2626';
  }
  if (eventTypeLabel?.toLowerCase().includes('cooperat') || (goldstein !== undefined && goldstein > 5)) {
    return '#16a34a';
  }
  if (eventTypeLabel?.toLowerCase().includes('protest')) {
    return '#f59e0b';
  }
  return '#3b82f6';
}

function escapeHtml(text?: string): string {
  if (!text) return '';
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}
