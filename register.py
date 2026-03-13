import sys
import os
import pickle
import pathlib

# 1. 모델 경로 강제 설정 (가장 중요)
# 가상환경 내에 설치된 모델의 실제 위치를 찾아내어 face_recognition에 알려줌
venv_site_packages = next(pathlib.Path(os.getcwd()).glob("h1/lib/python*/site-packages"))
sys.path.append(str(venv_site_packages))

try:
    import face_recognition_models
    import face_recognition
    # 라이브러리가 모델을 못 찾을 때를 대비해 내부 변수를 수동으로 업데이트
    face_recognition.api.face_recognition_models = face_recognition_models
    print("라이브러리 및 모델 경로 강제 매칭 성공!")
except Exception as e:
    print(f"로드 실패: {e}")
    sys.exit()

def register_faces(image_dir):
    known_encodings = []
    known_names = []

    print("--- 얼굴 등록 프로세스 시작 ---")
    
    if not os.path.exists(image_dir):
        print(f"에러: {image_dir} 폴더를 찾을 수 없습니다.")
        return

    for filename in os.listdir(image_dir):
        if filename.lower().endswith((".jpg", ".png", ".jpeg")):
            path = os.path.join(image_dir, filename)
            print(f"처리 중: {filename}...", end=" ", flush=True)
            
            try:
                image = face_recognition.load_image_file(path)
                encodings = face_recognition.face_encodings(image)
                
                if len(encodings) > 0:
                    known_encodings.append(encodings[0])
                    # 파일명에서 이름만 추출 (예: jang1 -> jang)
                    name = "".join([i for i in os.path.splitext(filename)[0] if not i.isdigit()])
                    known_names.append(name)
                    print("성공!")
                else:
                    print("실패 (얼굴 감지 안됨)")
            except Exception as e:
                print(f"에러: {e}")

    # 데이터 저장
    data = {"encodings": known_encodings, "names": known_names}
    with open("registered_faces.pkl", "wb") as f:
        pickle.dump(data, f)
    
    print("--------------------------------")
    print(f"완료! 'registered_faces.pkl' 파일이 생성되었습니다. (총 {len(known_names)}명)")

if __name__ == "__main__":
    register_faces("faces")