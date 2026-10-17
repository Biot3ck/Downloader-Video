// Dependency-free tests of header bounds and ZIP integrity. No DOM/network.
'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const zlib=require('node:zlib');
const image=require('./images.js');
function png(width,height){
  function chunk(type,bytes){const name=Buffer.from(type),size=Buffer.alloc(4),crc=Buffer.alloc(4);size.writeUInt32BE(bytes.length);crc.writeUInt32BE(image.crc32(Buffer.concat([name,bytes])));return Buffer.concat([size,name,bytes,crc]);}
  const header=Buffer.alloc(13);header.writeUInt32BE(width,0);header.writeUInt32BE(height,4);header[8]=8;header[9]=2;
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',zlib.deflateSync(Buffer.from([0,98,85,234]))),chunk('IEND',Buffer.alloc(0))]);
}
function file(bytes,name='a.png',type='image/png'){const blob=new Blob([bytes],{type});Object.defineProperty(blob,'name',{value:name});return blob;}
(async()=>{
  const first=png(1,1),second=png(1,1);
  assert.deepEqual(image.dimensions(first,first.length),{width:1,height:1,extension:'png',mime:'image/png'});
  await image.inspect(file(first));
  assert.equal(image.crc32(new TextEncoder().encode('123456789')),0xcbf43926);
  await assert.rejects(image.inspect(file(first,'evil.svg','image/svg+xml')));
  await assert.rejects(image.inspect(file(Buffer.from('<svg/>'),'a.png')));
  assert.throws(()=>image.dimensions(first.subarray(0,20),20));
  assert.throws(()=>image.dimensions(png(5000,5000),100),/16 megapixels/);
  assert.throws(()=>image.validateSelection(Array.from({length:21},()=>({size:1}))));
  assert.throws(()=>image.validateSelection([{size:0}]));
  assert.throws(()=>image.validateSelection([{size:11*1024*1024}]));
  assert.throws(()=>image.validateSelection(Array.from({length:6},()=>({size:10*1024*1024}))));
  const webp=new Uint8Array(30),view=new DataView(webp.buffer);webp.set(Buffer.from('RIFF'));view.setUint32(4,22,true);webp.set(Buffer.from('WEBPVP8X'),8);view.setUint32(16,10,true);
  assert.equal(image.dimensions(webp,30).extension,'webp');webp[20]=2;assert.throws(()=>image.dimensions(webp,30),/animation/);
  const jpeg=Buffer.from([255,216,255,192,0,8,8,0,2,0,3,0]);
  assert.equal(image.dimensions(jpeg,jpeg.length).width,3);
  assert.equal(image.dimensions(jpeg,jpeg.length).height,2);
  assert.throws(()=>image.zipImages([{name:'../escape.png',bytes:first}]));
  assert.throws(()=>image.zipImages([{name:'clipora-image-01.png',bytes:first},{name:'clipora-image-01.png',bytes:second}]));
  const bytes=Buffer.from(await image.zipImages([{name:'clipora-image-01.png',bytes:first},{name:'clipora-image-02.png',bytes:second}]).arrayBuffer());
  assert.equal(bytes.readUInt32LE(0),0x04034b50);assert.equal(bytes.readUInt32LE(bytes.length-22),0x06054b50);assert.equal(bytes.readUInt16LE(bytes.length-12),2);
  if(process.argv[2])fs.writeFileSync(process.argv[2],bytes,{flag:'wx',mode:0o600});
  console.log('PASS: image bounds, MIME mismatch, SSRF-free local ZIP, CRC32, filenames, JPEG/PNG/WebP headers');
})().catch(error=>{console.error(error);process.exitCode=1;});
