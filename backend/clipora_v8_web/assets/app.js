"use strict";
const form=document.getElementById('downloadForm');
const input=document.getElementById('url');
const button=document.getElementById('check-link');
const result=document.getElementById('result');
const mediaChoices=document.querySelectorAll('input[name="media_kind"]');
function selectedMedia(){return document.querySelector('input[name="media_kind"]:checked').value;}
function showMediaMode(){
  const images=selectedMedia()==='images';
  document.getElementById('url-label').textContent=images?'Image post URL':'Video URL';
  document.getElementById('media-help').textContent=images?'Photos, carousels and pins from TikTok, Instagram, and Pinterest.':'Video links from YouTube, TikTok, Instagram, and Pinterest.';
  input.placeholder=images?'Paste a TikTok photo post, Instagram post, or Pinterest pin link':'Paste a YouTube, TikTok, Instagram, or Pinterest link';
  result.textContent=images?'Paste an image post link to check its platform.':'Paste a video link to check its platform.';
  document.getElementById('sample-mode').hidden=images||!sampleAvailable;
  document.getElementById('image-sample-mode').hidden=!images||!sampleAvailable;
  if(images)document.getElementById('sample-video').pause();
}
let sampleAvailable=false;
mediaChoices.forEach(choice=>choice.addEventListener('change',showMediaMode));
const names={youtube:'YouTube',tiktok:'TikTok',instagram:'Instagram',pinterest:'Pinterest'};
form.addEventListener('submit',async event=>{
  event.preventDefault();if(button.disabled)return;
  const requestedMedia=selectedMedia();
  button.disabled=true;mediaChoices.forEach(choice=>{choice.disabled=true;});result.textContent='Checking your link…';
  try {
    const response=await fetch('/api/v8/validate',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({url:input.value.trim(),media_kind:requestedMedia}),signal:AbortSignal.timeout(10000),cache:'no-store'});
    const data=await response.json();
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Could not check this link.');
    if(data.media_kind!==requestedMedia||!Object.hasOwn(names,data.platform)||data.public_downloads_enabled!==false||data.network_access_performed!==false)
      throw Error('Unexpected server response. Please try again.');
    result.textContent=names[data.platform]+(requestedMedia==='images'?' image post link recognized. Image and album downloads are being prepared.':' video link recognized. Public downloads are being prepared.')+' This check did not contact the platform or verify the post contents.';
  }catch(error){result.textContent=error.name==='TimeoutError'?'The request timed out. Please try again.':error.message||'Connection lost. Please try again.';}
  finally{button.disabled=false;mediaChoices.forEach(choice=>{choice.disabled=false;});}
});
// Fixed local sample workflow. Public video URLs never enter this queue.
const samplePanel=document.getElementById('sample-mode');
const sampleStart=document.getElementById('sample-start');
const sampleCancel=document.getElementById('sample-cancel');
const sampleStatus=document.getElementById('sample-status');
const sampleVideo=document.getElementById('sample-video');
const sampleSave=document.getElementById('sample-save');
let sampleJob=null,sampleTimer=null,sampleStopped=false,sampleKey=null;
function rememberSample(value){try{if(value)sessionStorage.setItem('clipora.sample.job',value);else sessionStorage.removeItem('clipora.sample.job');}catch{}}
function rememberedSample(){try{return sessionStorage.getItem('clipora.sample.job');}catch{return null;}}
async function sampleRequest(path,options={}){
  const response=await fetch(path,{credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(15000),...options});
  const data=response.status===204?null:await response.json();
  if(!response.ok){const error=Error(typeof data?.detail==='string'?data.detail:'The sample could not be processed.');error.status=response.status;throw error;}
  return data;
}
function clearSampleMedia(){sampleVideo.pause();sampleVideo.removeAttribute('src');sampleVideo.load();sampleVideo.hidden=true;sampleSave.removeAttribute('href');sampleSave.hidden=true;}
function samplePath(job){if(!/^[0-9a-f]{32}$/.test(job))throw Error('Invalid sample job.');return '/api/v8/jobs/'+job;}
async function pollSample(){
  if(sampleStopped||!sampleJob)return;
  try{
    const state=await sampleRequest(samplePath(sampleJob));
    if(!['queued','processing','completed','failed'].includes(state.status))throw Error('Unexpected job status.');
    sampleStart.disabled=['queued','processing'].includes(state.status);
    sampleCancel.hidden=!sampleStart.disabled;sampleCancel.disabled=state.cancel_requested===true;
    if(state.status==='completed'){
      const file=samplePath(sampleJob)+'/file';sampleVideo.src=file;sampleVideo.hidden=false;sampleSave.href=file;sampleSave.hidden=false;
      sampleStatus.textContent='Your sample is ready. Preview it here or download the MP4.';sampleKey=null;rememberSample(sampleJob);return;
    }
    if(state.status==='failed'){
      sampleStatus.textContent=state.cancel_requested?'Sample download cancelled.':'The sample could not finish. You can try again.';
      sampleKey=null;rememberSample(null);return;
    }
    sampleStatus.textContent=state.cancel_requested?'Stopping the sample download…':state.status==='queued'?'Your sample is queued…':'Preparing your sample video…';
  }catch(error){
    if(error.status===404){sampleStatus.textContent='This sample has expired. Prepare a new one.';sampleJob=null;rememberSample(null);sampleStart.disabled=false;sampleCancel.hidden=true;return;}
    sampleStatus.textContent='Connection interrupted. Reconnecting to your sample…';
  }
  if(!sampleStopped)sampleTimer=setTimeout(pollSample,1200);
}
sampleStart.addEventListener('click',async()=>{
  if(sampleStart.disabled)return;
  sampleStart.disabled=true;clearSampleMedia();sampleStatus.textContent='Starting your sample…';
  try{
    await sampleRequest('/api/v8/session',{method:'POST'});
    sampleKey=sampleKey||crypto.randomUUID().replaceAll('-','');
    const job=await sampleRequest('/api/v8/samples',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':sampleKey},body:'{}'});
    samplePath(job.job_id);sampleJob=job.job_id;rememberSample(sampleJob);
    if(sampleTimer)clearTimeout(sampleTimer);await pollSample();
  }catch(error){sampleStart.disabled=false;sampleStatus.textContent=error.message||'Could not start the sample. Please try again.';}
});
sampleCancel.addEventListener('click',async()=>{
  if(!sampleJob||sampleCancel.disabled)return;
  sampleCancel.disabled=true;sampleStatus.textContent='Stopping the sample download…';
  try{await sampleRequest(samplePath(sampleJob)+'/cancel',{method:'POST'});}
  catch(error){sampleCancel.disabled=false;sampleStatus.textContent=error.message||'Could not cancel the sample.';}
});
async function initializeSample(){
  try{
    const config=await sampleRequest('/api/v8/ui/config');
    if(config.offline_sample_enabled!==true||config.public_downloads_enabled!==false)return;
    await sampleRequest('/api/v8/session',{method:'POST'});sampleAvailable=true;samplePanel.hidden=selectedMedia()==='images';
    document.getElementById('image-sample-mode').hidden=selectedMedia()!=='images';
    restoreImageSample();
    const previous=rememberedSample();if(previous&&/^[0-9a-f]{32}$/.test(previous)){sampleJob=previous;sampleStart.disabled=true;await pollSample();}
  }catch{samplePanel.hidden=true;}
}
window.addEventListener('pagehide',()=>{sampleStopped=true;if(sampleTimer)clearTimeout(sampleTimer);});
window.addEventListener('pageshow',event=>{if(event.persisted){sampleStopped=false;initializeSample();}});
initializeSample();

showMediaMode();


// Owned backend album fixture. Only same-origin job paths are used for media.
const imageSampleStart=document.getElementById('image-sample-start');
const imageSampleCancel=document.getElementById('image-sample-cancel');
const imageSampleStatus=document.getElementById('image-sample-status');
const imageSampleGallery=document.getElementById('image-sample-gallery');
const imageSampleZIP=document.getElementById('image-sample-zip');
let imageJob=null,imageKey=null,imageTimer=null,imageStopped=false;
function rememberImageJob(value){try{if(value)sessionStorage.setItem('clipora.sample.images.job',value);else sessionStorage.removeItem('clipora.sample.images.job');}catch{}}
function clearImageResult(){imageSampleGallery.replaceChildren();imageSampleZIP.removeAttribute('href');imageSampleZIP.hidden=true;}
function renderBackendAlbum(manifest){
  if(manifest.media_kind!=='images'||manifest.version!==1||!Array.isArray(manifest.items)||manifest.items.length<1||manifest.items.length>20||manifest.image_count!==manifest.items.length)throw Error('Invalid sample album.');
  const fragment=document.createDocumentFragment();
  manifest.items.forEach((item,index)=>{
    if(item.position!==index+1||!['image/png','image/jpeg','image/webp'].includes(item.mime))throw Error('Invalid sample image.');
    const path=samplePath(imageJob)+'/images/'+(index+1),card=document.createElement('figure'),img=document.createElement('img'),caption=document.createElement('figcaption'),link=document.createElement('a');
    img.src=path;img.alt='Backend sample image '+(index+1);img.loading='lazy';img.decoding='async';
    caption.textContent='Image '+(index+1)+' · '+item.mime.replace('image/','').toUpperCase();
    link.href=path;link.className='action secondary';link.textContent='Download image '+(index+1)+' ↓';link.download='clipora-sample-image-'+(index+1);
    card.append(img,caption,link);fragment.append(card);
  });
  imageSampleGallery.replaceChildren(fragment);imageSampleZIP.href=samplePath(imageJob)+'/album.zip';imageSampleZIP.hidden=false;
}
async function pollImageSample(){
  if(imageStopped||!imageJob)return;
  try{
    const job=await sampleRequest(samplePath(imageJob));
    if(!['queued','processing','completed','failed'].includes(job.status))throw Error('Unexpected image job status.');
    imageSampleStart.disabled=['queued','processing'].includes(job.status);imageSampleCancel.hidden=!imageSampleStart.disabled;imageSampleCancel.disabled=job.cancel_requested===true;
    if(job.status==='completed'){
      const manifest=await sampleRequest(samplePath(imageJob)+'/images');renderBackendAlbum(manifest);
      imageSampleStatus.textContent='Your sample album is ready. Download an image or the full ZIP.';imageKey=null;rememberImageJob(imageJob);return;
    }
    if(job.status==='failed'){
      clearImageResult();imageSampleStatus.textContent=job.cancel_requested?'Sample album cancelled.':'The sample album could not finish. Please try again.';imageKey=null;rememberImageJob(null);return;
    }
    imageSampleStatus.textContent=job.cancel_requested?'Stopping the sample album…':job.status==='queued'?'Your sample album is queued…':'Checking and preparing your sample images…';
  }catch(error){
    if(error.status===404){clearImageResult();imageSampleStatus.textContent='This sample album has expired. Prepare a new one.';imageSampleStart.disabled=false;imageSampleCancel.hidden=true;imageJob=null;rememberImageJob(null);return;}
    imageSampleStatus.textContent='Connection interrupted. Reconnecting to your album…';
  }
  if(!imageStopped)imageTimer=setTimeout(pollImageSample,1200);
}
function restoreImageSample(){
  let remembered=null;try{remembered=sessionStorage.getItem('clipora.sample.images.job');}catch{}
  if(remembered&&/^[0-9a-f]{32}$/.test(remembered)){imageJob=remembered;imageSampleStart.disabled=true;if(imageTimer)clearTimeout(imageTimer);pollImageSample();}
}
imageSampleStart.addEventListener('click',async()=>{
  if(imageSampleStart.disabled)return;
  imageSampleStart.disabled=true;clearImageResult();imageSampleStatus.textContent='Starting your sample album…';
  try{
    await sampleRequest('/api/v8/session',{method:'POST'});imageKey=imageKey||crypto.randomUUID().replaceAll('-','');
    const job=await sampleRequest('/api/v8/samples/images',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':imageKey},body:'{}'});
    samplePath(job.job_id);imageJob=job.job_id;rememberImageJob(imageJob);if(imageTimer)clearTimeout(imageTimer);await pollImageSample();
  }catch(error){imageSampleStart.disabled=false;imageSampleStatus.textContent=error.message||'Could not start the sample album.';}
});
imageSampleCancel.addEventListener('click',async()=>{
  if(!imageJob||imageSampleCancel.disabled)return;
  imageSampleCancel.disabled=true;imageSampleStatus.textContent='Stopping the sample album…';
  try{await sampleRequest(samplePath(imageJob)+'/cancel',{method:'POST'});}
  catch(error){imageSampleCancel.disabled=false;imageSampleStatus.textContent=error.message||'Could not stop the sample album.';}
});
window.addEventListener('pagehide',()=>{imageStopped=true;if(imageTimer)clearTimeout(imageTimer);});
window.addEventListener('pageshow',event=>{if(event.persisted)imageStopped=false;});
