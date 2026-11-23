"""Localização automática da webcam (com detector de rosto injetado: o que se testa é a geometria e a decisão de confiança)."""
import unittest

import numpy as np

from liveclips import camera_detect as cd

W,H=960,540


def frame(seed,cam=(0.74,0.04,0.24,0.32),border=True):
    """Jogo = ruído que muda a cada quadro; webcam = retângulo fixo com moldura clara e 'rosto' escuro no meio."""
    rng=np.random.default_rng(seed)
    img=rng.integers(20,200,(H,W,3),dtype=np.uint8)
    x,y,w,h=cam;x0,y0,x1,y1=int(x*W),int(y*H),int((x+w)*W),int((y+h)*H)
    img[y0:y1,x0:x1]=(90,110,130)
    if border:
        img[y0:y1,x0:x0+3]=255;img[y0:y1,x1-3:x1]=255;img[y0:y0+3,x0:x1]=255;img[y1-3:y1,x0:x1]=255
    return img


def iou(a,b):
    ax0,ay0,ax1,ay1=a[0],a[1],a[0]+a[2],a[1]+a[3];bx0,by0,bx1,by1=b[0],b[1],b[0]+b[2],b[1]+b[3]
    iw,ih=max(0,min(ax1,bx1)-max(ax0,bx0)),max(0,min(ay1,by1)-max(ay0,by0));inter=iw*ih
    return inter/((a[2]*a[3])+(b[2]*b[3])-inter)


TRUE=(0.74,0.04,0.24,0.32)
FACE=(0.74+0.24*0.30,0.04+0.32*0.22,0.24*0.40,0.32*0.45)        # rosto dentro da câmera


class EstimateTests(unittest.TestCase):
    def test_finds_the_webcam_rectangle_from_a_stable_face(self):
        images=[frame(i) for i in range(9)]
        result=cd.estimate(images,detector=lambda img:[FACE])
        self.assertTrue(result['found']);self.assertEqual(result['level'],'alta')
        self.assertGreater(iou(result['rect'],TRUE),0.75,result['rect'])

    def test_snaps_to_the_frame_border_when_the_camera_is_in_a_corner(self):
        cam=(0.76,0.0,0.24,0.34);images=[frame(i,cam) for i in range(9)]
        face=(0.76+0.24*0.3,0.34*0.25,0.24*0.4,0.34*0.45)
        result=cd.estimate(images,detector=lambda img:[face])
        x,y,w,h=result['rect'];self.assertAlmostEqual(y,0.0,places=2);self.assertAlmostEqual(x+w,1.0,places=2)

    def test_ignores_a_face_that_wanders_like_a_game_character(self):
        images=[frame(i) for i in range(9)];boxes=[(0.05+0.09*i,0.5,0.1,0.15) for i in range(9)]
        calls=iter(boxes)
        result=cd.estimate(images,detector=lambda img:[next(calls)])
        self.assertFalse(result['found']);self.assertIn('à mão',result['reason'])

    def test_no_face_at_all(self):
        result=cd.estimate([frame(i) for i in range(9)],detector=lambda img:[])
        self.assertFalse(result['found']);self.assertEqual(result['hits'],0)

    def test_medium_confidence_when_face_seen_in_few_frames(self):
        images=[frame(i) for i in range(9)];seen=iter([True,False,True,False,True,False,True,False,False])
        result=cd.estimate(images,detector=lambda img:[FACE] if next(seen) else [])
        self.assertTrue(result['found']);self.assertEqual(result['level'],'media')

    def test_rejects_an_implausibly_large_rectangle(self):
        big=(0.1,0.1,0.38,0.5)
        result=cd.estimate([frame(i) for i in range(9)],detector=lambda img:[big])
        self.assertFalse(result['found'])

    def test_rect_is_inside_the_image_and_valid_for_the_profile(self):
        from liveclips.store import profile_checked,DEFAULT_PROFILE
        result=cd.estimate([frame(i) for i in range(9)],detector=lambda img:[FACE])
        x,y,w,h=result['rect'];self.assertTrue(x>=0 and y>=0 and x+w<=1.00001 and y+h<=1.00001)
        profile_checked(dict(DEFAULT_PROFILE,camera_rect=result['rect']))


class DetectGuardTests(unittest.TestCase):
    def test_detect_never_raises_on_a_missing_video(self):
        result=cd.detect('/nao/existe.ts')
        self.assertFalse(result['found']);self.assertIn('falhou',result['reason'])

    def test_real_opencv_detector_does_not_crash_on_blank_frames(self):
        self.assertEqual(cd.detect_faces(np.zeros((540,960,3),dtype=np.uint8)),[])


if __name__=='__main__':
    unittest.main()
