import { useEffect, useRef, useState, type ChangeEvent } from 'react'
import { ImagePlus, X } from 'lucide-react'

function PhotoPreview({ file }: { file: File }) {
  const image = useRef<HTMLImageElement>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    const url = URL.createObjectURL(file)
    if (image.current) image.current.src = url
    return () => URL.revokeObjectURL(url)
  }, [file])
  return <>{failed && <span className="photo-fallback">Preview unavailable</span>}<img ref={image} alt={`Attachment: ${file.name}`} hidden={failed} onError={() => setFailed(true)} /></>
}

export function ComplaintPhotos({ files, onChange }: { files: File[]; onChange?: (files: File[]) => void }) {
  const [error, setError] = useState('')
  function choose(event: ChangeEvent<HTMLInputElement>) {
    const selected = Array.from(event.target.files || [])
    event.target.value = ''
    setError('')
    if (files.length + selected.length > 5) {
      setError('Choose up to five pictures in total.')
    } else if (selected.some(file => !['image/jpeg', 'image/png', 'image/webp'].includes(file.type))) {
      setError('Choose JPEG, PNG or WebP pictures only.')
    } else if (selected.some(file => file.size > 5 * 1024 * 1024 || file.size === 0)) {
      setError('Each picture must be non-empty and no larger than 5 MB.')
    } else {
      onChange?.([...files, ...selected])
    }
  }
  return <div className="complaint-photos">
    {onChange ? <div className="photo-picker">
      <ImagePlus size={22} aria-hidden="true" />
      <label htmlFor="complaint-pictures">Add pictures (optional)</label>
      <p id="picture-help">Up to 5 pictures, 5 MB each. JPEG, PNG or WebP. Local preview only; pictures are not uploaded or saved.</p>
      <input id="complaint-pictures" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={choose} aria-describedby="picture-help" />
    </div> : <h3>Pictures ({files.length})</h3>}
    {error && <p className="error-message" role="alert">{error}</p>}
    {!onChange && !files.length && <p className="muted">No pictures attached.</p>}
    <div className="photo-grid">{files.map((file, index) => <figure className="photo-item" key={`${file.name}-${file.lastModified}-${index}`}>
      <div className="photo-image"><PhotoPreview file={file} />
        {onChange && <button type="button" className="icon-button photo-remove" title={`Remove ${file.name}`} aria-label={`Remove ${file.name}`} onClick={() => { onChange(files.filter((_, position) => position !== index)); setError('') }}><X size={16} /></button>}
      </div>
      <figcaption>{file.name}<span>{(file.size / 1024 / 1024).toFixed(2)} MB</span></figcaption>
    </figure>)}</div>
  </div>
}