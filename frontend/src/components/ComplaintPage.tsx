import { useState, type FormEvent } from 'react'
import { Activity, ArrowLeft, ArrowRight, CheckCircle2, ClipboardList, MapPin, Pencil, ShieldCheck } from 'lucide-react'
import './complaint.css'
import { ComplaintChannels } from './ComplaintChannels'
import { ComplaintPhotos } from './ComplaintPhotos'

export function ComplaintPage() {
  const [area, setArea] = useState('Rural')
  const [district, setDistrict] = useState('')
  const [locality, setLocality] = useState('')
  const [administration, setAdministration] = useState('')
  const [category, setCategory] = useState('Roads')
  const [language, setLanguage] = useState('Kannada')
  const [details, setDetails] = useState('')
  const [landmark, setLandmark] = useState('')
  const [review, setReview] = useState(false)
  const [finished, setFinished] = useState(false)
  const [pictures, setPictures] = useState<File[]>([])
  const ready = district.trim() && locality.trim() && details.trim()

  function preview(event: FormEvent) {
    event.preventDefault()
    if (ready) setReview(true)
  }

  return <div className="citizen-shell">
    <a className="skip-link" href="#complaint-main">Skip to content</a>
    <header className="citizen-header">
      <a href="/" className="brand" aria-label="CivicPulse home"><span className="brand-mark"><Activity size={22} /></span><span>CivicPulse<span className="brand-ai">AI</span></span></a>
      <a href="/" className="secondary-button"><ArrowLeft size={16} />Policymaker dashboard</a>
    </header>
    <main id="complaint-main" className="citizen-main">
      <div className="citizen-heading"><div><p className="eyebrow">KARNATAKA / CITIZEN SERVICES</p><h1>Register a complaint</h1></div><span className="demo-label">UI PREVIEW ONLY</span></div>
      <p className="preview-notice"><ShieldCheck size={18} />Sample form only. No calls, messages, microphone access, AI processing, uploads, or saved complaints. Phone numbers and transcripts are placeholders. This is not an official government complaint channel.</p>
      <div className="citizen-layout">
        <aside className="citizen-aside">
          <img src="/complaint-map.svg" alt="" width="220" height="140" />
          <h2>Your locality.<br />Your concerns.</h2>
          <ol className="complaint-steps"><li className={!review ? 'active' : ''}><span>01</span>Issue &amp; location</li><li className={review ? 'active' : ''}><span>02</span>Review complaint</li></ol>
          <p>Do not enter Aadhaar numbers, passwords, or other sensitive personal information.</p>
          <p>For emergencies, contact the appropriate emergency service.</p>
        </aside>
        {!review ? <form className="complaint-form" onSubmit={preview}>
          <section><h2><MapPin size={19} />Where is the issue?</h2>
            <fieldset className="area-choice"><legend>Area type</legend>{['Rural', 'Urban'].map(value => <label key={value}><input type="radio" name="area" checked={area === value} onChange={() => { setArea(value); setAdministration(''); setLocality('') }} />{value}</label>)}</fieldset>
            <div className="complaint-fields">
              <label>State<input value="Karnataka" readOnly /></label>
              <label>District<input value={district} onChange={event => setDistrict(event.target.value)} placeholder="e.g. Bengaluru Urban" required maxLength={200} /></label>
              <label>{area === 'Rural' ? 'Taluk / Gram Panchayat (optional)' : 'Municipality / corporation (optional)'}<input value={administration} onChange={event => setAdministration(event.target.value)} maxLength={200} /></label>
              <label>{area === 'Rural' ? 'Village' : 'Ward / locality'}<input value={locality} onChange={event => setLocality(event.target.value)} placeholder={area === 'Rural' ? 'Village name' : 'e.g. Whitefield'} required maxLength={200} /></label>
            </div>
            <label>Nearby landmark (optional)<input value={landmark} onChange={event => setLandmark(event.target.value)} placeholder="Road, bus stop, school, or other nearby place" maxLength={300} /></label>
          </section>
          <section><h2><ClipboardList size={19} />What needs attention?</h2>
            <div className="complaint-fields">
              <label>Category<select value={category} onChange={event => setCategory(event.target.value)}>{['Roads', 'Water', 'Electricity', 'Healthcare', 'Education', 'Other'].map(value => <option key={value}>{value}</option>)}</select></label>
              <label>Complaint language<select value={language} onChange={event => setLanguage(event.target.value)}>{['Kannada', 'Hindi', 'English'].map(value => <option key={value}>{value}</option>)}</select></label>
            </div>
            <ComplaintChannels remaining={5000 - details.length - (details ? 2 : 0)} onUse={text => { setDetails(previous => previous ? `${previous}\n\n${text}` : text); setLanguage('English') }} />
            <label>Issue details<textarea value={details} onChange={event => setDetails(event.target.value)} required maxLength={5000} rows={5} placeholder="Describe the issue, where it is happening, and who is affected." /></label>
            <p className="field-meta text-right">{details.length.toLocaleString()} / 5,000</p>
            <ComplaintPhotos files={pictures} onChange={setPictures} />
          </section>
          <div className="complaint-actions"><span className="muted">No personal contact details required for this preview.</span><button className="primary-button" disabled={!ready} type="submit">Review complaint<ArrowRight size={16} /></button></div>
        </form> : <section className="complaint-review" aria-labelledby="review-title">
          <h2 id="review-title">Review your complaint</h2>
          <dl className="facts">{[
            ['State', 'Karnataka'], ['Area type', area], ['District', district],
            ['Village / locality', locality], ['Local administration', administration || 'Not provided'],
            ['Landmark', landmark || 'Not provided'], ['Category', category], ['Language', language],
          ].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl>
          <h3>Issue details</h3><p className="complaint-description">{details}</p>
          <ComplaintPhotos files={pictures} />
          {finished && <p role="status" className="success-message"><CheckCircle2 size={18} />Preview complete. Nothing was submitted or saved. No complaint reference has been issued.</p>}
          <div className="complaint-actions"><button className="secondary-button" onClick={() => { setReview(false); setFinished(false) }}><Pencil size={16} />Edit complaint</button><button className="primary-button" disabled={finished} onClick={() => setFinished(true)}><CheckCircle2 size={16} />Finish preview</button></div>
        </section>}
      </div>
      <footer className="page-footer">CivicPulse AI / Karnataka citizen intake preview</footer>
    </main>
  </div>
}