'use strict';
// Product surface: link recognition only, plus bundled sample media when the
// explicit local demo preview is enabled. No worker, no network, no public gate.
const views={
  video:{label:'Video Downloader',line:'Your videos.',accent:'One simple link.',description:'A simpler way to save the videos you love. Start with a link from your favorite platform.',kind:'video',caption:'Start with your video link',input:'Video URL',placeholder:'Paste a video link here',help:'YouTube, TikTok, Instagram, and Pinterest links.',platforms:['YouTube','TikTok','Instagram','Pinterest']},
  photo:{label:'Photo Downloader',line:'Your photos.',accent:'One simple link.',description:'From a single photo to an entire carousel. Keep the moments you want to come back to.',kind:'images',caption:'Start with your photo post link',input:'Photo post URL',placeholder:'Paste a photo post or pin link here',help:'TikTok photo posts, Instagram posts, and Pinterest pins.',platforms:['TikTok','Instagram','Pinterest']}
};
const names={youtube:'YouTube',tiktok:'TikTok',instagram:'Instagram',pinterest:'Pinterest'};
const form=document.getElementById('downloadForm'),input=document.getElementById('url'),button=document.getElementById('check-link');
const pasteButton=document.getElementById('paste-link');
const result=document.getElementById('result'),resultTitle=document.getElementById('result-title'),resultDescription=document.getElementById('result-description');
const previewCard=document.getElementById('preview-card'),previewVideo=document.getElementById('preview-video');
const previewImage=document.getElementById('preview-image'),previewPlaceholder=document.getElementById('preview-placeholder');
const previewTitle=document.getElementById('preview-title'),previewCaption=document.getElementById('preview-caption');
const previewPlatform=document.getElementById('preview-platform'),previewDuration=document.getElementById('preview-duration');
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
  image:'Bundled sample: 1280×720 image. Not the post you pasted.'
};
const unavailableNotes={
  video:'Video downloads are not available in this build.',
  hd:'HD downloads are not available in this build.',
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
function hidePreview(){
  previewCard.hidden=true;
  previewVideo.hidden=true;previewImage.hidden=true;previewPlaceholder.hidden=false;
  previewVideo.removeAttribute('src');previewVideo.removeAttribute('poster');previewImage.removeAttribute('src');
  previewTitle.textContent='';previewCaption.textContent='';previewPlatform.textContent='';previewDuration.textContent='';
  previewPlaceholder.textContent='Loading preview…';
}
function hideDownload(){
  formatPicker.hidden=true;actions.hidden=true;downloadStatus.textContent='';hidePreview();
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
for(const format of ['video','hd']){
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
async function loadPreview(view,operation){
  previewCard.hidden=false;
  previewVideo.hidden=true;previewImage.hidden=true;previewPlaceholder.hidden=false;
  previewPlaceholder.textContent='Loading preview…';
  previewTitle.textContent='';previewCaption.textContent='';previewPlatform.textContent='';previewDuration.textContent='';
  try{
    const response=await fetch('/api/v8/demo/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:input.value.trim(),media_kind:view.kind}),cache:'no-store',credentials:'same-origin'});
    if(operation!==revision)return;
    let data=null;
    try{data=await response.json();}catch{data=null;}
    if(operation!==revision)return;
    if(!response.ok||!data||data.sample!==true||data.network_access_performed!==false||typeof data.preview_url!=='string'||!data.preview_url.startsWith('/api/v8/demo/preview/')||typeof data.caption!=='string'||!Object.hasOwn(names,data.platform))throw Error('preview');
    previewPlaceholder.hidden=true;
    if(view.kind==='images'){
      previewImage.setAttribute('src',data.preview_url);previewImage.hidden=false;
    }else{
      previewVideo.setAttribute('src',data.preview_url);
      if(typeof data.poster_url==='string'&&data.poster_url.startsWith('/api/v8/demo/preview/'))previewVideo.setAttribute('poster',data.poster_url);
      previewVideo.hidden=false;
    }
    previewTitle.textContent=typeof data.title==='string'&&data.title?data.title:names[data.platform]+' sample';
    previewCaption.textContent=data.caption;
    previewPlatform.textContent=names[data.platform];
    const meta=[];
    if(typeof data.duration_seconds==='number')meta.push(data.duration_seconds+'s');
    if(typeof data.width==='number'&&typeof data.height==='number')meta.push(data.width+'×'+data.height);
    previewDuration.textContent=meta.join(' · ');
  }catch{
    if(operation!==revision)return;
    previewPlaceholder.hidden=false;previewPlaceholder.textContent='Preview unavailable right now.';
  }
}
async function check(){
  if(button.disabled||!views[currentView]?.kind)return;
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
      showResult(names[data.platform]+' link recognized','Preview and download options are below. Everything here comes from the bundled sample.');
      loadPreview(view,operation);
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
}
form.addEventListener('submit',event=>{event.preventDefault();return check();});
function withTimeout(promise,milliseconds){
  return new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(new Error('timeout')),milliseconds);
    promise.then(value=>{clearTimeout(timer);resolve(value);},error=>{clearTimeout(timer);reject(error);});
  });
}
pasteButton.addEventListener('click',async()=>{
  if(pasteButton.disabled)return;
  pasteButton.disabled=true;
  try{
    if(typeof navigator==='undefined'||!navigator.clipboard||typeof navigator.clipboard.readText!=='function')throw Error('unsupported');
    // A pending browser permission prompt never settles, so cap the wait.
    const text=(await withTimeout(navigator.clipboard.readText(),8000)).trim();
    if(!text){showResult('Clipboard is empty','Copy a post link first, then press Paste again.',true);return;}
    if(text.length>2048){showResult('That link is too long','Use a post link up to 2048 characters.',true);return;}
    input.value=text;
    resetCheck();
    await check();
  }catch(error){
    input.focus();
    if(error?.message==='timeout')showResult('Clipboard permission was not granted','Allow clipboard access for this page, or paste the link with Cmd+V.',true);
    else showResult('Could not read the clipboard','Your browser blocked clipboard access. Paste the link with Cmd+V instead.',true);
  }finally{
    pasteButton.disabled=false;
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
