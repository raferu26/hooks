"""Localiza a webcam sozinho: acha o rosto em vários quadros da gravação e estima o retângulo da câmera.

Heurístico e conservador (nunca promete acerto):
1. tira ~9 quadros espalhados pelo primeiro segmento;
2. detecta rostos (MediaPipe se disponível; senão o detector de rostos do OpenCV, que vem junto da instalação);
3. só aceita um rosto que aparece quase no mesmo lugar em vários quadros (rosto de personagem do jogo se mexe);
4. expande o rosto para o retângulo da câmera e encosta as bordas nas linhas retas fortes do quadro médio (a moldura
   da webcam é fixa; o jogo, não);
5. devolve nível de confiança. 'alta' pode ser aplicada sozinha; 'media' vira sugestão para o usuário confirmar.

Retângulo no mesmo formato do perfil: [x, y, largura, altura], tudo de 0 a 1.
"""
from pathlib import Path
import statistics
import subprocess
import tempfile
import os

from . import media

FRAMES=12
MIN_FACE=0.03          # largura mínima do rosto, relativa à largura da imagem
MAX_FACE=0.40


def grab_frames(video,folder,count=FRAMES,width=960):
    """Extrai `count` quadros do vídeo para a pasta (PNG). Devolve a lista de caminhos."""
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
    interval=4.0
    pattern=str(folder/'q%02d.png')
    cp=subprocess.run([media.tool('ffmpeg'),'-nostdin','-hide_banner','-loglevel','error','-y','-t','58','-i',str(video),
                       '-vf',f'fps=1/{interval:g},scale={width}:-2','-frames:v',str(count),pattern],
                      stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,creationflags=flags)
    if cp.returncode:raise RuntimeError(cp.stderr.decode('utf-8',errors='replace')[-400:] or 'Não consegui extrair quadros do vídeo.')
    return sorted(folder.glob('q*.png'))


def _mediapipe_faces(image):
    """Rostos pelo MediaPipe (modelo vem embutido no pacote). None se não estiver disponível nesta versão."""
    try:
        import mediapipe as mp
        import cv2
        solution=mp.solutions.face_detection
    except Exception:
        return None
    try:
        height,width=image.shape[:2]
        with solution.FaceDetection(model_selection=1,min_detection_confidence=0.55) as detector:
            result=detector.process(cv2.cvtColor(image,cv2.COLOR_BGR2RGB))
        boxes=[]
        for item in (result.detections or []):
            box=item.location_data.relative_bounding_box
            boxes.append((box.xmin,box.ymin,box.width,box.height))
        return boxes
    except Exception:
        return None


def _opencv_faces(image):
    import cv2
    path=Path(cv2.data.haarcascades)/'haarcascade_frontalface_default.xml'
    if not path.is_file():return []
    cascade=cv2.CascadeClassifier(str(path))
    if cascade.empty():return []
    height,width=image.shape[:2]
    gray=cv2.equalizeHist(cv2.cvtColor(image,cv2.COLOR_BGR2GRAY))
    found=cascade.detectMultiScale(gray,scaleFactor=1.1,minNeighbors=6,minSize=(max(24,int(width*MIN_FACE)),)*2)
    return [(x/width,y/height,w/width,h/height) for x,y,w,h in found]


def detect_faces(image):
    """Caixas de rosto normalizadas (x, y, w, h). Usa o MediaPipe se der, senão o OpenCV."""
    boxes=_mediapipe_faces(image)
    if boxes is None:boxes=_opencv_faces(image)
    return [b for b in boxes if MIN_FACE<=b[2]<=MAX_FACE and b[3]>0]


def _consensus(per_frame):
    """Escolhe o rosto que reaparece no mesmo lugar. -> (caixa mediana, acertos, desvio relativo ao tamanho do rosto)."""
    candidates=[(i,b) for i,boxes in enumerate(per_frame) for b in boxes]
    best=None
    for _,seed in candidates:
        sx,sy=seed[0]+seed[2]/2,seed[1]+seed[3]/2
        group={}
        for i,b in candidates:
            if abs(b[0]+b[2]/2-sx)<=seed[2]*0.6 and abs(b[1]+b[3]/2-sy)<=seed[3]*0.6:
                if i not in group or b[2]*b[3]>group[i][2]*group[i][3]:group[i]=b
        if best is None or len(group)>len(best):best=group
    if not best:return None,0,1.0
    boxes=list(best.values())
    median=tuple(statistics.median(b[k] for b in boxes) for k in range(4))
    spread=max(max(abs(b[0]+b[2]/2-(median[0]+median[2]/2)),abs(b[1]+b[3]/2-(median[1]+median[3]/2))) for b in boxes)/max(median[2],1e-6)
    return median,len(boxes),spread


def expand(face):
    """Do rosto para a câmera: sobra acima da cabeça, ombros abaixo, e margem dos lados. Cola na borda do quadro se estiver perto."""
    fx,fy,fw,fh=face
    cx=fx+fw/2
    left,right=cx-1.15*fw,cx+1.15*fw
    top,bottom=fy-0.65*fh,fy+fh+0.85*fh
    left,top,right,bottom=max(0.0,left),max(0.0,top),min(1.0,right),min(1.0,bottom)
    if left<0.08:left=0.0
    if top<0.08:top=0.0
    if right>0.92:right=1.0
    if bottom>0.92:bottom=1.0
    return [left,top,right-left,bottom-top]


def snap_edges(rect,mean_image,face):
    """Encosta cada lado nas linhas retas mais fortes por perto (moldura fixa da webcam). -> (rect, lados ajustados)."""
    import cv2
    import numpy as np
    height,width=mean_image.shape[:2]
    gray=cv2.cvtColor(mean_image,cv2.COLOR_BGR2GRAY).astype('float32')
    sx=np.abs(cv2.Sobel(gray,cv2.CV_32F,1,0,ksize=3));sy=np.abs(cv2.Sobel(gray,cv2.CV_32F,0,1,ksize=3))
    x0,y0=rect[0]*width,rect[1]*height;x1,y1=(rect[0]+rect[2])*width,(rect[1]+rect[3])*height
    reach=max(6,int(face[2]*width*0.5))
    snapped=0

    def best(profile,at,limit):
        lo,hi=max(0,int(at)-reach),min(limit-1,int(at)+reach)
        if hi-lo<4:return at,False
        window=profile[lo:hi+1]
        peak=int(np.argmax(window));floor=float(np.median(window))+1e-6
        if window[peak]>=2.0*floor and window[peak]>0:return float(lo+peak),True
        return at,False

    ys=slice(int(y0+(y1-y0)*0.1),max(int(y0+(y1-y0)*0.1)+1,int(y1-(y1-y0)*0.1)))
    xs=slice(int(x0+(x1-x0)*0.1),max(int(x0+(x1-x0)*0.1)+1,int(x1-(x1-x0)*0.1)))
    col=sx[ys,:].sum(axis=0);row=sy[:,xs].sum(axis=1)
    if x0>3:
        x0,ok=best(col,x0,width);snapped+=ok
    if x1<width-3:
        x1,ok=best(col,x1,width);snapped+=ok
    if y0>3:
        y0,ok=best(row,y0,height);snapped+=ok
    if y1<height-3:
        y1,ok=best(row,y1,height);snapped+=ok
    out=[max(0.0,x0/width),max(0.0,y0/height),0.0,0.0]
    out[2]=min(1.0,x1/width)-out[0];out[3]=min(1.0,y1/height)-out[1]
    return out,int(snapped)


def estimate(images,detector=detect_faces):
    """Núcleo (sem ffmpeg): `images` = quadros BGR do OpenCV. Devolve o resultado da detecção."""
    import numpy as np
    per_frame=[detector(image) for image in images]
    face,hits,spread=_consensus(per_frame)
    total=len(images)
    if face is None or hits<2:
        return dict(found=False,level=None,hits=hits,frames=total,reason='Não encontrei um rosto que apareça no mesmo lugar em vários quadros. Marque a webcam à mão.')
    mean=np.mean(np.stack(images).astype('float32'),axis=0).astype('uint8')
    rect,snapped=snap_edges(expand(face),mean,face)
    if rect[2]<0.06 or rect[3]<0.06 or rect[2]>0.6 or rect[3]>0.6:
        return dict(found=False,level=None,hits=hits,frames=total,reason='O retângulo estimado ficou com tamanho improvável. Marque a webcam à mão.')
    ratio=hits/max(total,1)
    level='alta' if ratio>=0.6 and spread<=0.35 else 'media' if ratio>=0.35 and spread<=0.6 else None
    rect=[round(float(v),6) for v in rect]
    if level is None:
        return dict(found=False,level=None,hits=hits,frames=total,reason='O rosto apareceu em poucos quadros ou mudou de lugar. Marque a webcam à mão.')
    return dict(found=True,rect=rect,level=level,hits=hits,frames=total,snapped=snapped,
                face=[round(float(v),4) for v in face],
                reason=f'Rosto em {hits} de {total} quadros, {snapped} borda(s) ajustada(s) à moldura.')


def detect(video,count=FRAMES,detector=detect_faces):
    """Detecta a webcam de um segmento de vídeo. Nunca levanta erro: devolve found=False com o motivo."""
    try:
        import cv2
        with tempfile.TemporaryDirectory(prefix='hooks_cam_') as folder:
            files=grab_frames(video,folder,count)
            images=[image for image in (cv2.imread(str(f)) for f in files) if image is not None]
            if len(images)<3:
                return dict(found=False,level=None,hits=0,frames=len(images),reason='Poucos quadros legíveis no vídeo para localizar a webcam.')
            return estimate(images,detector)
    except Exception as exc:
        return dict(found=False,level=None,hits=0,frames=0,reason='A localização automática falhou: '+str(exc)[:160])
