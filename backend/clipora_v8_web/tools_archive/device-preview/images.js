'use strict';
// This entire gallery runs locally. It has no fetch, upload, or platform adapter.
(()=>{
  const MAX_COUNT=20,MAX_FILE=10*1024*1024,MAX_TOTAL=50*1024*1024,MAX_PIXELS=16000000;
  const ascii=(bytes,start,length)=>String.fromCharCode(...bytes.subarray(start,start+length));
  function dimensions(bytes,fileSize){
    const view=new DataView(bytes.buffer,bytes.byteOffset,bytes.byteLength);
    let width,height,extension,mime;
    if(bytes.length>=33&&bytes[0]===137&&ascii(bytes,1,7)==='PNG\r\n\x1a\n'&&view.getUint32(8)===13&&ascii(bytes,12,4)==='IHDR'){
      width=view.getUint32(16);height=view.getUint32(20);extension='png';mime='image/png';
    }else if(bytes.length>=4&&bytes[0]===255&&bytes[1]===216){
      let pos=2;
      while(pos<bytes.length){
        if(bytes[pos++]!==255)break;
        while(pos<bytes.length&&bytes[pos]===255)pos++;
        if(pos>=bytes.length)break;
        const marker=bytes[pos++];
        if(marker===217||marker===218)break;
        if(marker===1||(marker>=208&&marker<=215))continue;
        if(pos+2>bytes.length)break;
        const length=view.getUint16(pos);
        if(length<2||pos+length>bytes.length)break;
        if([192,193,194,195,197,198,199,201,202,203,205,206,207].includes(marker)){
          if(length<8)break;
          height=view.getUint16(pos+3);width=view.getUint16(pos+5);extension='jpg';mime='image/jpeg';break;
        }
        pos+=length;
      }
    }else if(bytes.length>=30&&ascii(bytes,0,4)==='RIFF'&&ascii(bytes,8,4)==='WEBP'&&view.getUint32(4,true)+8===fileSize){
      const chunk=ascii(bytes,12,4),size=view.getUint32(16,true);
      if(size+20>fileSize)throw Error('The WebP image is incomplete.');
      if(chunk==='VP8X'&&size===10){
        if(bytes[20]&2)throw Error('Choose a still WebP image, not an animation.');
        width=1+bytes[24]+bytes[25]*256+bytes[26]*65536;height=1+bytes[27]+bytes[28]*256+bytes[29]*65536;
      }else if(chunk==='VP8 '&&size>=10&&bytes[23]===157&&bytes[24]===1&&bytes[25]===42){
        width=view.getUint16(26,true)&16383;height=view.getUint16(28,true)&16383;
      }else if(chunk==='VP8L'&&size>=5&&bytes[20]===47){
        const bits=view.getUint32(21,true);width=1+(bits&16383);height=1+((bits>>>14)&16383);
      }
      if(width){extension='webp';mime='image/webp';}
    }
    if(!width||!height||!extension)throw Error('Choose a valid JPEG, PNG, or still WebP image.');
    if(width>16384||height>16384)throw Error('Each image dimension must be at most 16,384 pixels.');
    if(width*height>MAX_PIXELS)throw Error('Each image must be at most 16 megapixels.');
    return {width,height,extension,mime};
  }
  function validateSelection(files){
    if(files.length<1||files.length>MAX_COUNT)throw Error('Choose between 1 and 20 images.');
    let total=0;
    for(const file of files){
      if(!Number.isSafeInteger(file.size)||file.size<=0||file.size>MAX_FILE)throw Error('Each image must be non-empty and at most 10 MiB.');
      total+=file.size;
    }
    if(total>MAX_TOTAL)throw Error('The whole album must be at most 50 MiB.');
  }
  async function inspect(file){
    const bytes=new Uint8Array(await file.slice(0,262144).arrayBuffer());
    const info=dimensions(bytes,file.size);
    const suffix=/\.([a-z0-9]+)$/i.exec(file.name)?.[1].toLowerCase();
    const expected=info.extension==='jpg'?['jpg','jpeg']:[info.extension];
    if(!expected.includes(suffix)||(file.type&&file.type!==info.mime))throw Error('The file extension or type does not match its image contents.');
    return info;
  }
  const table=Uint32Array.from({length:256},(_,n)=>{for(let i=0;i<8;i++)n=n&1?0xedb88320^(n>>>1):n>>>1;return n>>>0;});
  function crc32(bytes){let crc=0xffffffff;for(const byte of bytes)crc=table[(crc^byte)&255]^(crc>>>8);return (crc^0xffffffff)>>>0;}
  function zipImages(entries){
    validateSelection(entries.map(entry=>({size:entry.bytes.length})));
    const parts=[],directory=[],names=new Set();let offset=0,directorySize=0;
    for(const {name,bytes} of entries){
      if(!(bytes instanceof Uint8Array)||!/^clipora-image-\d{2}\.(jpg|png|webp)$/.test(name)||names.has(name))throw Error('Invalid album entry.');
      names.add(name);
      const filename=new TextEncoder().encode(name),crc=crc32(bytes);
      const local=new Uint8Array(30+filename.length),l=new DataView(local.buffer);
      l.setUint32(0,0x04034b50,true);l.setUint16(4,20,true);l.setUint16(6,0x800,true);l.setUint16(12,33,true);
      l.setUint32(14,crc,true);l.setUint32(18,bytes.length,true);l.setUint32(22,bytes.length,true);l.setUint16(26,filename.length,true);local.set(filename,30);
      const central=new Uint8Array(46+filename.length),c=new DataView(central.buffer);
      c.setUint32(0,0x02014b50,true);c.setUint16(4,20,true);c.setUint16(6,20,true);c.setUint16(8,0x800,true);c.setUint16(14,33,true);
      c.setUint32(16,crc,true);c.setUint32(20,bytes.length,true);c.setUint32(24,bytes.length,true);c.setUint16(28,filename.length,true);c.setUint32(42,offset,true);central.set(filename,46);
      parts.push(local,bytes);directory.push(central);offset+=local.length+bytes.length;directorySize+=central.length;
    }
    const end=new Uint8Array(22),e=new DataView(end.buffer);e.setUint32(0,0x06054b50,true);e.setUint16(8,entries.length,true);e.setUint16(10,entries.length,true);e.setUint32(12,directorySize,true);e.setUint32(16,offset,true);
    return new Blob([...parts,...directory,end],{type:'application/zip'});
  }
  const api=Object.freeze({dimensions,inspect,validateSelection,crc32,zipImages});
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  if(typeof document==='undefined')return;
  const input=document.getElementById('image-files'),gallery=document.getElementById('image-gallery'),status=document.getElementById('image-status');
  const prepare=document.getElementById('image-zip'),save=document.getElementById('image-zip-save'),clear=document.getElementById('image-clear');
  let generation=0,entries=[],urls=[],archive=null;
  function reset(){
    generation++;gallery.replaceChildren();entries=[];
    for(const url of urls)URL.revokeObjectURL(url);urls=[];
    if(archive)URL.revokeObjectURL(archive);archive=null;
    save.removeAttribute('href');save.hidden=true;prepare.hidden=true;prepare.disabled=false;clear.hidden=true;
  }
  input.addEventListener('change',async()=>{
    reset();const current=generation,files=Array.from(input.files||[]);
    if(!files.length){status.textContent='No images selected.';return;}
    status.textContent='Checking your images on this device…';
    try{
      validateSelection(files);const checked=[];let pixels=0;
      for(const file of files){const info=await inspect(file);if(current!==generation)return;pixels+=info.width*info.height;if(pixels>32000000)throw Error('The whole album must be at most 32 megapixels.');checked.push({file,info});}
      for(const [index,{file,info}] of checked.entries()){
        const url=URL.createObjectURL(new Blob([file],{type:info.mime}));urls.push(url);
        const name='clipora-image-'+String(index+1).padStart(2,'0')+'.'+info.extension;
        const card=document.createElement('figure'),image=document.createElement('img'),caption=document.createElement('figcaption'),link=document.createElement('a');
        image.src=url;image.alt='Selected image '+(index+1);image.loading='lazy';image.decoding='async';
        image.addEventListener('error',()=>{if(current===generation)status.textContent='One image could not be displayed. Clear the album and choose valid images.';});
        caption.textContent='Image '+(index+1)+' · '+info.width+' × '+info.height;
        link.href=url;link.download=name;link.className='action secondary';link.textContent='Download image '+(index+1)+' ↓';
        card.append(image,caption,link);gallery.append(card);entries.push({file,name});
      }
      prepare.hidden=false;clear.hidden=false;
      status.textContent=entries.length+' image'+(entries.length===1?'':'s')+' ready. Save each image or prepare the album ZIP. Nothing was uploaded.';
    }catch(error){if(current!==generation)return;reset();input.value='';status.textContent=error.message||'These images could not be opened.';}
  });
  prepare.addEventListener('click',async()=>{
    if(prepare.disabled||!entries.length)return;
    const current=generation,selected=entries.slice();prepare.disabled=true;status.textContent='Preparing your ZIP on this device…';
    try{
      const packed=[];
      for(const {file,name} of selected){const bytes=new Uint8Array(await file.arrayBuffer());if(current!==generation)return;packed.push({name,bytes});}
      const blob=zipImages(packed);if(current!==generation)return;
      if(archive)URL.revokeObjectURL(archive);archive=URL.createObjectURL(blob);save.href=archive;save.hidden=false;prepare.hidden=true;
      status.textContent='Your album ZIP is ready. It contains the original images in selection order.';
    }catch(error){if(current===generation){prepare.disabled=false;status.textContent=error.message||'Could not prepare the ZIP.';}}
  });
  clear.addEventListener('click',()=>{reset();input.value='';status.textContent='Images cleared. Choose another album to continue.';});
  window.addEventListener('pagehide',()=>{reset();input.value='';status.textContent='No images selected.';});
})();
