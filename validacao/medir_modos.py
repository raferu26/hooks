import subprocess,time,re,sys,json
sys.path.insert(0,__import__('os').path.join(__import__('os').path.dirname(__file__),'..'))
from liveclips import hardware
src='src.mp4'
# fonte com movimento, ruído e degradê (sintética: não substitui clipe real)
subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y','-f','lavfi','-i','mandelbrot=size=1080x1920:rate=30,noise=alls=12:allf=t,format=yuv420p','-t','4','-c:v','libx264','-crf','0','-preset','ultrafast',src],check=True)
out={}
for m in ('rapido','equilibrado','qualidade','entrega'):
    args=hardware.choose('cpu',mode=m)[1];t=time.time()
    subprocess.run(['ffmpeg','-nostdin','-loglevel','error','-y','-i',src,*args,'-pix_fmt','yuv420p','-threads','4',m+'.mp4'],check=True)
    el=time.time()-t
    r=subprocess.run(['ffmpeg','-nostdin','-i',m+'.mp4','-i',src,'-lavfi','[0][1]ssim;[0][1]psnr','-f','null','-'],capture_output=True,text=True).stderr
    ssim=re.search(r'SSIM.*All:([\d.]+)',r).group(1);psnr=re.search(r'PSNR.*average:([\d.inf]+)',r).group(1)
    import os
    out[m]=dict(segundos=round(el,1),kbps=round(os.path.getsize(m+'.mp4')*8/4/1000),ssim=float(ssim),psnr=psnr,args=' '.join(args))
print(json.dumps(out,indent=1))
