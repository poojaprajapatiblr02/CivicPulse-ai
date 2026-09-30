import { useState } from 'react'
import { AudioLines, Check, FileAudio, Headphones, MessageCircle, MessageSquareText, Mic, Pencil, Phone, RotateCcw, Square, Upload, UserRound, UsersRound } from 'lucide-react'

const channels = [
  { name: 'Write', icon: Pencil },
  { name: 'Record voice', icon: Mic },
  { name: 'Voice note', icon: FileAudio },
  { name: 'Call / IVR', icon: Phone },
  { name: 'WhatsApp', icon: MessageCircle },
  { name: 'SMS', icon: MessageSquareText },
  { name: 'Assisted entry', icon: UsersRound },
] as const
type Channel = typeof channels[number]['name']
const sampleTranscript = 'The road near our bus stop has potholes. It becomes difficult to travel when it rains. Please arrange an inspection and repairs.'
const conversations = {
  'Call / IVR': {
    title: 'Speak to the complaint helpline', contact: '+91 XXXXX XXXXX', note: 'Placeholder number / no call service connected',
    agent: 'Welcome to CivicPulse. Choose Kannada, Hindi or English, then tell us your district, village or ward, and the issue.',
    citizen: 'English. Whitefield, Bengaluru Urban. The road near our bus stop needs repair.',
    reply: 'Sample read-back: a road issue in Whitefield. Please confirm or correct the location and description. No complaint is registered in this preview.',
  },
  WhatsApp: {
    title: 'Message or send a voice note', contact: '+91 XXXXX XXXXX', note: 'Placeholder WhatsApp number / no messages sent',
    agent: 'Choose a language. Share the issue and your district and village or locality. A voice note or photo could accompany your complaint.',
    citizen: 'There are potholes near the bus stop in Whitefield, Bengaluru Urban.',
    reply: 'Sample review: Roads / Whitefield. Check the details before confirming. This conversation is not connected to WhatsApp.',
  },
  SMS: {
    title: 'Send a text complaint', contact: 'XXXXX', note: 'Placeholder short code / SMS service not connected',
    agent: 'Sample message: district; village or locality; issue. Do not include sensitive personal information.',
    citizen: 'Bengaluru Urban; Whitefield; damaged road near the bus stop.',
    reply: 'Sample reply: please confirm the location. No SMS or tracking reference is issued by this preview.',
  },
  'Assisted entry': {
    title: 'Register with a local officer', contact: 'Gram Panchayat / ward office', note: 'Sample assisted intake / no appointment or officer assigned',
    agent: 'Tell the officer your preferred language, location and concern. Ask them to read the details back before you confirm.',
    citizen: 'Please record the damaged road near our bus stop. I would like to review the description.',
    reply: 'Sample officer read-back: road repair requested near the bus stop. Location and details still require confirmation.',
  },
}

function ChannelPreview({ channel, remaining, onUse }: { channel: Channel; remaining: number; onUse: (text: string) => void }) {
  const [recording, setRecording] = useState(false)
  const [transcriptVisible, setTranscriptVisible] = useState(false)
  const [transcript, setTranscript] = useState(sampleTranscript)
  const [added, setAdded] = useState(false)
  const [fileName, setFileName] = useState('')
  const [fileError, setFileError] = useState('')
  const [conversationVisible, setConversationVisible] = useState(false)

  if (channel === 'Write') return null
  if (channel === 'Record voice' || channel === 'Voice note') return <div className="intake-panel">
    <div className="intake-panel-heading"><span className="intake-icon"><AudioLines size={22} /></span><div><h3>{channel === 'Record voice' ? 'Speak your concern' : 'Attach a voice note'}</h3><p>SIMULATED AUDIO / NO TRANSCRIPTION SERVICE</p></div></div>
    {channel === 'Record voice' ? <>
      <div className={`voice-session ${recording ? 'is-recording' : ''}`}>
        <div className="voice-wave" aria-hidden="true">{Array.from({ length: 23 }, (_, index) => <span key={index} style={{ height: `${12 + (index * 17 % 43)}px`, animationDelay: `${index * 0.04}s` }} />)}</div>
        <p role="status">{recording ? 'Sample recording in progress. Microphone is off.' : 'Sample recorder / microphone is off.'}</p>
        {!recording ? <button type="button" className="primary-button" onClick={() => { setRecording(true); setTranscriptVisible(false); setAdded(false); setTranscript(sampleTranscript) }}><Mic size={16} />Start sample recording</button> : <button type="button" className="secondary-button" onClick={() => { setRecording(false); setTranscriptVisible(true) }}><Square size={16} />Stop sample recording</button>}
      </div>
    </> : <div className="voice-upload">
      <Upload size={24} aria-hidden="true" />
      <label>Choose an audio file (local preview only)<input type="file" accept="audio/*" onChange={event => {
        const file = event.target.files?.[0]
        setFileName(''); setFileError(''); setTranscriptVisible(false); setAdded(false); setTranscript(sampleTranscript)
        if (!file) return
        if (!file.type.startsWith('audio/')) { setFileError('Choose an audio file. Nothing was uploaded.'); return }
        if (file.size > 10 * 1024 * 1024) { setFileError('Choose a file up to 10 MB. Nothing was uploaded.'); return }
        setFileName(file.name)
      }} /></label>
      <p className="muted">Audio only / up to 10 MB / filename stays in this page</p>
      {fileError && <p role="alert" className="error-message">{fileError}</p>}
      {fileName && <p className="selected-audio"><FileAudio size={16} /><span>{fileName}</span></p>}
      <button type="button" className="secondary-button" disabled={!fileName} onClick={() => setTranscriptVisible(true)}><AudioLines size={16} />Show sample transcript</button>
    </div>}
    {transcriptVisible && <div className="transcript-preview">
      <label>Sample transcript (English)<textarea rows={4} value={transcript} maxLength={5000} onChange={event => { setTranscript(event.target.value); setAdded(false) }} /></label>
      <p className="sample-disclosure">{channel === 'Voice note' ? 'Not transcribed from your file. ' : 'Not recorded from your microphone. '}This is editable example text, not AI output.</p>
      {transcript.trim().length > remaining && <p role="alert" className="error-message">This sample exceeds the space left in Issue details. Shorten it before adding.</p>}
      <div className="transcript-actions"><button type="button" className="primary-button" disabled={added || !transcript.trim() || transcript.trim().length > remaining} onClick={() => { onUse(transcript.trim()); setAdded(true) }}><Check size={16} />{added ? 'Add sample to complaint' : 'Add sample to complaint'}</button><button type="button" className="icon-button" aria-label="Reset sample transcript" title="Reset sample transcript" onClick={() => { setTranscript(sampleTranscript); setAdded(false) }}><RotateCcw size={16} /></button></div>
      {added && <p role="status" className="sample-added">Sample added to Issue details. Language set to English. Nothing was submitted.</p>}
    </div>}
  </div>

  const conversation = conversations[channel]
  return <div className="intake-panel">
    <div className="intake-panel-heading"><span className="intake-icon"><Headphones size={22} /></span><div><h3>{conversation.title}</h3><p>CHANNEL PREVIEW / NOT CONNECTED</p></div></div>
    <p className="contact-placeholder">{conversation.contact}</p><p className="sample-disclosure">{conversation.note}</p>
    <button type="button" className="secondary-button" onClick={() => setConversationVisible(value => !value)}><MessageSquareText size={16} />{conversationVisible ? 'Close conversation' : 'Preview conversation'}</button>
    {conversationVisible && <div className="sample-conversation" role="region" aria-label={`${channel} sample conversation`}>
      <p className="conversation-caption">Sample exchange / not connected</p>
      {[{ role: 'Intake service', text: conversation.agent }, { role: 'Citizen', text: conversation.citizen }, { role: 'Review', text: conversation.reply }].map(message => <div className="conversation-line" key={message.role}><UserRound size={16} aria-hidden="true" /><div><h4>{message.role}</h4><p>{message.text}</p></div></div>)}
    </div>}
  </div>
}

export function ComplaintChannels({ remaining, onUse }: { remaining: number; onUse: (text: string) => void }) {
  const [channel, setChannel] = useState<Channel>('Write')
  return <div className="complaint-channels">
    <fieldset className="intake-choices"><legend>How would you like to share the issue?</legend>
      {channels.map(({ name, icon: Icon }) => <label key={name}><input type="radio" name="intake-channel" checked={channel === name} onChange={() => setChannel(name)} /><Icon size={18} aria-hidden="true" /><span>{name}</span></label>)}
    </fieldset>
    <ChannelPreview key={channel} channel={channel} remaining={remaining} onUse={onUse} />
  </div>
}