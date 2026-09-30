import { useEffect, useState } from 'react'
import { divIcon, latLngBounds } from 'leaflet'
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import type { Hotspot, Priority } from '../types/dashboard'
import { AreaFacts } from './Evidence'

function MapPosition({ hotspots, selected }: { hotspots: Hotspot[]; selected?: Hotspot }) {
  const map = useMap()
  useEffect(() => {
    if (selected) map.setView([selected.latitude, selected.longitude], 11)
    else if (hotspots.length) map.fitBounds(latLngBounds(hotspots.map(item => [item.latitude, item.longitude])), { padding: [36, 36], maxZoom: 11 })
    else map.setView([22.5, 79], 5)
  }, [map, hotspots, selected])
  return null
}

export function HotspotMap({ hotspots, priorities, selectedId, onSelect }: {
  hotspots: Hotspot[]; priorities: Priority[]; selectedId: string; onSelect: (id: string) => void
}) {
  const [tileError, setTileError] = useState(false)
  const groups = new Map<string, Hotspot[]>()
  for (const hotspot of hotspots) {
    const key = `${hotspot.latitude},${hotspot.longitude}`
    groups.set(key, [...(groups.get(key) || []), hotspot])
  }
  return <div className="map-frame" aria-label="Demand hotspot map">
    <MapContainer center={[22.5, 79]} zoom={5} scrollWheelZoom={false} className="hotspot-map">
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors' eventHandlers={{ tileerror: () => setTileError(true) }} />
      <MapPosition hotspots={hotspots} selected={hotspots.find(item => item.hotspot_id === selectedId)} />
      {[...groups.entries()].map(([key, group]) => <Marker key={key}
        position={[group[0].latitude, group[0].longitude]}
        title={`View ${group[0].location_name}`}
        icon={divIcon({ className: `hotspot-marker ${group.some(item => item.hotspot_id === selectedId) ? 'selected' : ''}`, html: `<span aria-hidden="true">${group.length}</span>`, iconSize: [32, 32], iconAnchor: [16, 16] })}
        eventHandlers={{ click: () => onSelect(group[0].hotspot_id) }}>
        <Popup minWidth={220} maxWidth={300}>
          {group.map(hotspot => <div className="popup-area" key={hotspot.hotspot_id}>
            <AreaFacts hotspot={hotspot} priority={priorities.find(item => item.hotspot_id === hotspot.hotspot_id && item.created_at === hotspot.created_at)} />
            <button className="text-button" onClick={() => onSelect(hotspot.hotspot_id)}>Select {hotspot.category}</button>
          </div>)}
        </Popup>
      </Marker>)}
    </MapContainer>
    {tileError && <p className="map-notice" role="status">Basemap unavailable. Hotspot coordinates and the priority table remain available.</p>}
  </div>
}