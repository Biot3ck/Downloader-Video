'use strict';
// Product surface: link recognition only, plus bundled sample files when the
// explicit local demo preview is enabled. No worker, no network, no public gate.
const views={
  video:{label:'Video Downloader',line:'Your videos.',accent:'One simple link.',description:'A simpler way to save the videos you love. Start with a link from your favorite platform.',kind:'video',caption:'Start with your video link',input:'Video URL',placeholder:'Paste a video link here',help:'YouTube, TikTok, Instagram, and Pinterest links.',platforms:['YouTube','TikTok','Instagram','Pinterest']},
  photo:{label:'Photo Downloader',line:'Your photos.',accent:'One simple link.',description:'From a single photo to an entire carousel. Keep the moments you want to come back to.',kind:'images',caption:'Start with your photo post link',input:'Photo post URL',placeholder:'Paste a photo post or pin link here',help:'TikTok photo posts, Instagram posts, and Pinterest pins.',platforms:['TikTok','Instagram','Pinterest']},
  audio:{label:'Audio Downloader',line:'Your audio.',accent:'Keep the sound.',description:'A dedicated place for audio from your videos. Audio downloads are not available yet.'},
  history:{label:'History',line:'Your downloads.',accent:'In one place.',description:'A place for completed downloads, with clear file availability and expiry.'}
};
const names={youtube:'YouTube',tiktok:'TikTok',instagram:'Instagram',pinterest:'Pinterest'};
const form=document.getElementById('downloadForm'),input=document.getElementById('url'),button=document.getElementById('check-link');
const result=document.getElementById('result'),resultTitle=document.getElementById('result-title'),resultDescription=document.getElementById('result-description');
const formatPicker=document.getElementById('video-formats'),formatNote=document.getElementById('format-note');
const actions=document.getElementById('download-actions'),downloadButton=document.getElementById('download-file');
const downloadLabel=document.getElementById('download-button-label'),downloadStatus=document.getElementById('download-status');
const availabilityText=document.getElementById('availability-text'),noticeText=document.getElementById('download-notice-text');
const links=document.querySelectorAll('.navigation [data-view]');
let currentView=null,controller=null,revision=0,recognized=null,demoEnabled=false,downloading=false;
const drafts={video:'',photo:''};
const sampleNotes={
  video:'Bundled sample: 640×360 video, 3 seconds. Not the post you pasted.',
  hd:'Bundled sample: 1280×720 video, 3 seconds. Not the post you pasted.',
  mp3:'Bundled sample: MP3 audio, 3 seconds. Not the post you pasted.',
  image:'Bundled sample: 1280×720 image. Not the post you pasted.'
};
const unavailableNotes={
  video:'Video downloads are not available in this build.',
  hd:'HD downloads are not available in this build.',
  mp3:'MP3 extraction is not available in this build.',
  image:'Image downloads are not available in this build.'
};
function currentFormat(){
  if(views[currentView]?.kind==='images')return 'image';
  const checked=document.querySelector('input[name="download-type"]:checked');
  return checked?.value||'video';
}
function updateFormatNote(){
  const key=currentFormat();
  formatNote.textContent=demoEnabled?(sampleNotes[key]||''):(unavailableNotes[key]||'');
}
function hideDownload(){
  formatPicker.hidden=true;actions.hidden=true;downloadStatus.textContent='';
}
function showResult(title,description,isError=false){
  resultTitle.textContent=title;resultDescription.textContent=description;result.classList.toggle('error',isError);result.hidden=false;
}
function resetCheck(){
  controller?.abort();controller=null;revision++;
  button.disabled=false;button.textContent='Check link →';form.removeAttribute('aria-busy');result.hidden=true;
  recognized=null;hideDownload();
}
input.addEventListener('input',resetCheck);
for(const format of ['video','hd','mp3']){
  document.getElementById('format-'+format).addEventListener('change',()=>{
    downloadStatus.textContent='';updateFormatNote();
  });
}
function navigate(focus=false){
  const key=location.hash.slice(1),next=Object.hasOwn(views,key)?key:'video';
  if(currentView===next)return;
  if(currentView==='video'||currentView==='photo')drafts[currentView]=input.value;
  resetCheck();
  currentView=next;const view=views[next];
  links.forEach(link=>{if(link.dataset.view===next)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});
  document.getElementById('feature-label').textContent=view.label;
  document.getElementById('hero-line').textContent=view.line;document.getElementById('hero-accent').textContent=view.accent;
  document.getElementById('hero-description').textContent=view.description;document.title=view.label+' · Clipora';
  document.getElementById('link-view').hidden=!view.kind;
  document.getElementById('audio-view').hidden=next!=='audio';document.getElementById('history-view').hidden=next!=='history';
  result.hidden=true;form.removeAttribute('aria-busy');
  availabilityText.textContent='Downloads unavailable';
  noticeText.textContent='Public downloads are currently unavailable. You can check whether your link uses a supported platform.';
  if(view.kind){
    input.value=drafts[next];document.getElementById('url-label').textContent=view.input;input.placeholder=view.placeholder;
    document.getElementById('form-caption').textContent=view.caption;document.getElementById('platform-help').textContent=view.help;
    const list=document.getElementById('platform-list');list.replaceChildren();
    view.platforms.forEach(name=>{const item=document.createElement('li');item.textContent=name;list.append(item);});
  }
  if(focus)document.getElementById('page-title').focus({preventScroll:true});
}
form.addEventListener('submit',async event=>{
  event.preventDefault();if(button.disabled||!views[currentView]?.kind)return;
  const view=views[currentView],operation=++revision,requestController=new AbortController();controller=requestController;
  button.disabled=true;button.textContent='Checking…';form.setAttribute('aria-busy','true');
  showResult('Checking your link','One moment, please.');
  const timeout=setTimeout(()=>requestController.abort(),10000);
  try{
    const response=await fetch('/api/v8/validate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:input.value.trim(),media_kind:view.kind}),signal:requestController.signal,cache:'no-store',credentials:'same-origin'});
    if(operation!==revision)return;
    // Handle service errors before parsing: proxies may return HTML or no body.
    if(response.status===429)throw Error('Too many checks. Please wait a moment and try again.');
    if(response.status>=500)throw Error('Clipora is temporarily unavailable. Please try again shortly.');
    let data;
    try{data=await response.json();}catch{throw Error('We could not check this link. Please try again.');}
    if(operation!==revision)return;
    if(!response.ok)throw Error([400,422].includes(response.status)&&typeof data?.detail==='string'?data.detail:'We could not check this link. Please try again.');
    if(!data||data.media_kind!==view.kind||!Object.hasOwn(names,data.platform)||data.public_downloads_enabled!==false||data.network_access_performed!==false)throw Error('This link could not be checked. Please try again.');
    demoEnabled=data.demo_downloads_enabled===true;
    recognized={url:input.value.trim(),kind:view.kind,platform:data.platform};
    formatPicker.hidden=view.kind!=='video';
    updateFormatNote();
    if(demoEnabled){
      actions.hidden=false;
      downloadLabel.textContent=view.kind==='images'?'Download sample image':'Download sample';
      availabilityText.textContent='Demo · sample file';
      noticeText.textContent='Demo mode returns a bundled sample file. The post you pasted is never downloaded.';
      showResult(names[data.platform]+' link recognized','Choose a download type below. This demo returns a bundled sample file, not the post you pasted.');
    }else{
      actions.hidden=true;downloadStatus.textContent='';
      showResult(names[data.platform]+' link recognized','Downloads are not available in this build. The platform was recognized only; the post itself was not inspected.');
    }
  }catch(error){
    if(operation!==revision)return;
    showResult('Could not check this link',error.name==='AbortError'?'The check timed out. Please try again.':error instanceof TypeError?'Could not connect to Clipora. Please try again.':error.message||'Please try again.',true);
  }finally{
    clearTimeout(timeout);
    if(operation===revision){button.disabled=false;button.textContent='Check link →';form.removeAttribute('aria-busy');controller=null;}
  }
});
downloadButton.addEventListener('click',async()=>{
  if(!recognized||downloading)return;
  const format=currentFormat();
  downloading=true;downloadButton.disabled=true;downloadStatus.textContent='Preparing your sample file…';
  try{
    const response=await fetch('/api/v8/demo/download',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:recognized.url,media_kind:recognized.kind,format}),cache:'no-store',credentials:'same-origin'});
    if(response.status===429)throw Error('Too many requests. Please wait a moment and try again.');
    if(response.status>=500)throw Error('The sample file is unavailable right now.');
    let data;
    try{data=await response.json();}catch{throw Error('The sample file could not be prepared.');}
    if(!response.ok)throw Error([400,422].includes(response.status)&&typeof data?.detail==='string'?data.detail:'The sample file could not be prepared.');
    if(!data||data.sample!==true||data.network_access_performed!==false||typeof data.url!=='string'||!data.url.startsWith('/api/v8/demo/file/'))throw Error('The sample file could not be prepared.');
    const filename=typeof data.filename==='string'?data.filename:'clipora-sample';
    downloadStatus.textContent='Sample file ready: '+filename;
    const link=document.createElement('a');
    link.href=data.url;link.download=filename;link.rel='noopener';
    if(typeof link.click==='function')link.click();
  }catch(error){
    downloadStatus.textContent=error.message||'The sample file could not be prepared.';
  }finally{
    downloading=false;downloadButton.disabled=false;
  }
});
window.addEventListener('hashchange',()=>navigate(true));
document.querySelector('.skip-link').addEventListener('click',event=>{event.preventDefault();document.getElementById('main').focus();});
window.addEventListener('pagehide',()=>{if(currentView==='video'||currentView==='photo')drafts[currentView]=input.value;controller?.abort();revision++;});
window.addEventListener('pageshow',event=>{if(event.persisted){currentView=null;navigate();}});
navigate();
