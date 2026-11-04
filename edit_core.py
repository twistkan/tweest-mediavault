"""Read-only photo editing recipes. Only explicit exports write new files."""
from dataclasses import dataclass,replace
from io import BytesIO
from pathlib import Path
import math
import os
import numpy as np
from PIL import Image,ImageOps

@dataclass(frozen=True)
class EditState:
    turns:int=0
    flip_x:bool=False
    flip_y:bool=False
    straighten:float=0
    crop:tuple=(0.,0.,1.,1.)
    exposure:float=0
    brightness:int=0
    contrast:int=0
    highlights:int=0
    shadows:int=0
    saturation:int=0
    vibrance:int=0

class EditHistory:
    def __init__(self):self.states=[EditState()]; self.index=0
    @property
    def current(self):return self.states[self.index]
    def push(self,state):
        if state==self.current:return
        self.states=self.states[:self.index+1]+[state]
        if len(self.states)>60:self.states=self.states[-60:]
        self.index=len(self.states)-1
    def undo(self):self.index=max(0,self.index-1); return self.current
    def redo(self):self.index=min(len(self.states)-1,self.index+1); return self.current

def load_photo(path):
    with Image.open(path) as source:
        image=ImageOps.exif_transpose(source)
        # Normalise tagged colour spaces before using the sRGB adjustment pipeline.
        profile=source.info.get('icc_profile')
        if profile:
            from PIL import ImageCms
            image=ImageCms.profileToProfile(image,ImageCms.ImageCmsProfile(BytesIO(profile)),ImageCms.createProfile('sRGB'),outputMode='RGBA')
        return image.convert('RGBA')

def geometry(image,state,apply_crop=True):
    output=image.copy() if image.mode=='RGBA' else image.convert('RGBA')
    if state.turns%4:output=output.rotate(-90*(state.turns%4),expand=True)
    if state.flip_x:output=ImageOps.mirror(output)
    if state.flip_y:output=ImageOps.flip(output)
    if state.straighten:
        angle=max(-15,min(15,state.straighten)); width,height=output.size
        output=output.rotate(angle,resample=Image.Resampling.BICUBIC,expand=True)
        radians=math.radians(abs(angle)); cosine,sine=math.cos(radians),math.sin(radians)
        scale=min(width/(width*cosine+height*sine),height/(width*sine+height*cosine))
        w=max(1,int(width*scale)-2); h=max(1,int(height*scale)-2)
        x=(output.width-w)//2; y=(output.height-h)//2
        output=output.crop((x,y,x+w,y+h))
    if apply_crop and state.crop!=(0.,0.,1.,1.):
        x0,y0,x1,y1=state.crop
        left=max(0,min(output.width-1,round(x0*output.width)))
        top=max(0,min(output.height-1,round(y0*output.height)))
        right=max(left+1,min(output.width,round(x1*output.width)))
        bottom=max(top+1,min(output.height,round(y1*output.height)))
        output=output.crop((left,top,right,bottom))
    return output

def render(image,state,apply_crop=True):
    output=geometry(image,state,apply_crop)
    if not any([state.exposure,state.brightness,state.contrast,state.highlights,state.shadows,state.saturation,state.vibrance]):return output
    pixels=np.asarray(output,dtype=np.uint8); rgb=pixels[:,:,:3].astype(np.float32)/255
    if state.exposure:
        rgb=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
        rgb*=2**state.exposure
        rgb=np.where(rgb<=.0031308,rgb*12.92,1.055*np.maximum(rgb,0)**(1/2.4)-.055)
    if state.brightness:rgb+=state.brightness/100*.25
    if state.contrast:rgb=(rgb-.5)*(2**(state.contrast/100))+.5
    if state.highlights or state.shadows:
        luminance=np.clip(rgb[:,:,0]*.2126+rgb[:,:,1]*.7152+rgb[:,:,2]*.0722,0,1)
        adjustment=state.shadows/100*.35*(1-luminance)**2+state.highlights/100*.35*luminance**2
        rgb+=adjustment[:,:,None]
    if state.vibrance or state.saturation:
        rgb=np.clip(rgb,0,1)
        luminance=(rgb[:,:,0]*.2126+rgb[:,:,1]*.7152+rgb[:,:,2]*.0722)[:,:,None]
        if state.vibrance:
            strongest=np.max(rgb,axis=2); weakest=np.min(rgb,axis=2)
            muted_weight=1-(strongest-weakest)/np.maximum(strongest,.0001)
            factor=1+state.vibrance/100*muted_weight
            rgb=luminance+(rgb-luminance)*factor[:,:,None]
        if state.saturation:rgb=luminance+(rgb-luminance)*(1+state.saturation/100)
    result=np.empty(pixels.shape,dtype=np.uint8)
    result[:,:,:3]=np.rint(np.clip(rgb,0,1)*255).astype(np.uint8); result[:,:,3]=pixels[:,:,3]
    return Image.fromarray(result)

def export_copy(source_path,image,state,destination,quality=92):
    source=Path(source_path); target=Path(destination)
    if target.resolve()==source.resolve() or (target.exists() and os.path.samefile(source,target)):
        raise ValueError('The original cannot be overwritten. Choose a new filename.')
    extension=target.suffix.lower()
    if extension not in ['.jpg','.jpeg','.png']:raise ValueError('Choose JPEG (.jpg) or PNG (.png).')
    if target.exists():raise FileExistsError('That file already exists. Choose a new filename.')
    edited=render(image,state); edited.info.clear(); buffer=BytesIO()
    if extension in ['.jpg','.jpeg']:
        background=Image.new('RGB',edited.size,'white'); background.paste(edited,mask=edited.getchannel('A'))
        background.save(buffer,format='JPEG',quality=max(60,min(100,int(quality))),subsampling=0)
    else:edited.save(buffer,format='PNG')
    # Exclusive creation never overwrites originals, aliases or existing exports.
    with target.open('xb') as stream:
        try:stream.write(buffer.getbuffer())
        except Exception:
            stream.close(); target.unlink(missing_ok=True); raise
    return target
