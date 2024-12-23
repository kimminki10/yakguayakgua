from typing import List, Dict
#커스텀 비전 라이브러리 추가
# Azure의 Custom Vision 라이브러리를 추가. 예측을 위하여 prediction을 포함
# OpenAPI스펙에 맞춰서 Authentication을 처리할 수 있도록 해주는 코드
from azure.cognitiveservices.vision.customvision.prediction import CustomVisionPredictionClient
from msrest.authentication import ApiKeyCredentials

from collections import defaultdict
from bs4 import BeautifulSoup

import gradio as gr
import requests

# 프로젝트 이후 api키 비공개 처리
import apikeys

from PIL import Image

#Custom Vision Web에 있는 값을 설정하여 클라이언트 인증
# 사용자가 만든 AI 모델의 예측 기능을 사용하기 위한 endpoint 지정
# KEY 값 지정
# 프로젝트 ID 지정
# 모델명 지정
prediction_endpoint = apikeys.prediction_endpoint
prediction_key = apikeys.prediction_key
project_id = apikeys.project_id
model_name = apikeys.model_name
 
# 앞에서 지정한 API KEY를 써서 커스텀 비전 모델을 사용할 클라이언트를 인증
credentials = ApiKeyCredentials(in_headers={"Prediction-key": prediction_key})
# endpoint를 써서 클라이언트 등록
predictor = CustomVisionPredictionClient(endpoint=prediction_endpoint, credentials=credentials)


def predict(image_path:str, threshold:int=50) -> List[str]:
    """ custom vision을 사용해서 이미지 분석 약 이름 리스트 반환 """
    # 이미지 파일을 바이너리 모드로 열어서 Custom Vision 모델에 전달
    # 모델이 감지한 예측 결과 중 확률이 threshold보다 높은 태그 이름을 반환
    with open(image_path, 'rb') as image_data:
        results = predictor.detect_image(project_id, model_name, image_data)
        for prediction in results.predictions:
            print(f"{prediction.tag_name}: {prediction.probability*100:.2f}%")
        return [ prediction.tag_name for prediction in results.predictions if prediction.probability*100 > threshold ]
    return [] # 예측이 없을 경우 빈 리스트 반환


def item_seq_list(name:str, page:int=1, numOfRows:int=10) -> List[str]:
    """ 약 이름을 통해 품목번호 리스트 반환 """
    # API 요청을 통해 특정 의약품 이름에 해당하는 ITEM_SEQ 리스트를 가져옴
    # item_name 파라미터로 약물 이름을 검색하며, 페이지 번호와 행 개수를 설정 가능
    servicekey = apikeys.item_seq_list_servicekey
    url = apikeys.item_seq_list_url
    params = {
        "serviceKey": servicekey,
        "pageNo": page,
        "numOfRows": numOfRows,
        "item_name": name,
        "type": "json"
    }
    res = requests.get(url, params=params)
    if res.status_code != 200:
        return []
    data = res.json()
    items = data['body']
    # 검색 결과가 없을 경우 빈 리스트 반환
    if items.get('totalCount', 0) == 0:
        return []
    # ITEM_SEQ 리스트 반환
    return [items['items'][0]['ITEM_SEQ']]


def drug_info(name:str, item_seq:str) -> Dict[str, str]:
    """ 품목번호를 통해 약 정보 반환 """
    # 의약품 상세 정보를 가져와서 사전에 저장
    # 웹 페이지에서 특정 선택자(selector)를 통해 원하는 항목 텍스트를 추출
    ret = {}
    selectors = {
        "효능": "#_ee_doc",
        #"용법": "#_ud_doc",
        #"주의사항": "#_nb_doc",
        #"기타정보": "#scroll_07",
        #"기본정보": "#content > section > div.drug_info_top.notPkInfo.not_button > div.r_sec > table",
    }
    url = f"{apikeys.drug_info_url}{item_seq}"
    res = requests.get(url)
    if res.status_code != 200:
        return ret
    ret['약이름'] = name
    soup = BeautifulSoup(res.text, "html.parser")
    # 각 선택자로부터 정보 추출하여 사전에 저장
    for key, selector in selectors.items():
        item = soup.select_one(selector)
        if item:
            ret[key] = item.text
    img = soup.select_one("#scroll_01 > div > div > img")
    if img:
        ret['이미지'] = f"![{item_seq}]({img['src']})"
    # DUR 정보 추가
    oldman = dur_odsn_atent_info(item_seq)
    if oldman:
        ret['노인주의'] = [f"{item['INGR_NAME']}: 주의필요" for item in oldman]

    pwnm = dur_pwnm_taboo_info(item_seq)
    if pwnm:
        ret['임부금기'] = [f"{item['INGR_NAME']}: {item['PROHBT_CONTENT']}" for item in pwnm]

    seobangjeong = dur_seobangjeong_partitn_atent_info(item_seq)
    if seobangjeong:
        ret['서방정분할주의'] = [f"{item['PROHBT_CONTENT']}" for item in seobangjeong]

    age_taboo = dur_SpcifyAgrdeTaboo_info(item_seq)
    if age_taboo:
        ret['특정연령금기'] = [f"{item['INGR_NAME']}: {item['PROHBT_CONTENT']}" for item in age_taboo]
    return ret


def dur_info(item_seq:str, url:str):
    """ 품목명을 통해 DUR 정보 반환 """
    servicekey = apikeys.dur_info_servicekey
    base_url = apikeys.dur_info_servicekey
    url = f"{base_url}/{url}"
    params = {
        "serviceKey": servicekey,
        "pageNo": 1,
        "numOfRows": 100,
        "itemSeq": item_seq,
        "type": "json"
    }
    res = requests.get(url, params=params)
    if res.status_code != 200: # 정상 응답이 아닌 경우
        return []
    data = res.json()
    items = data['body']
    if items.get('totalCount', 0) == 0:
        return []
    return items['items']
    

def dur_odsn_atent_info(item_seq:str) -> Dict[str, str]:
    """ 노인주의 정보 조회 
    res ex: 196000010
    {
        'TYPE_NAME': '노인주의',
        'MIX_TYPE': '단일',
        'INGR_CODE': 'D000893',
        'INGR_ENG_NAME': 'Chlorpheniramine',
        'INGR_NAME': '클로르페니라민',
        'MIX_INGR': '[M223211]클로르페니라민말레산염',
        'FORM_NAME': '용액주사제',
        'ITEM_SEQ': '196000010',
        'ITEM_NAME': '페니라민주사(클로르페니라민말레산염)',
        'ITEM_PERMIT_DATE': '19600721',
        'ENTP_NAME': '(주)유한양행',
        'CHART': '무색 투명한 액이 충전된 앰플',
        'CLASS_CODE': '01410',
        'CLASS_NAME': '항히스타민제',
        'ETC_OTC_NAME': '전문의약품',
        'MAIN_INGR': '[M223211]클로르페니라민말레산염',
        'NOTIFICATION_DATE': '20200924',
        'PROHBT_CONTENT': None,
        'REMARK': None,
        'INGR_ENG_NAME_FULL': 'Chlorpheniramine(클로르페니라민)',
        'CHANGE_DATE': '20140521'
    }
    """
    return dur_info(item_seq, "getOdsnAtentInfoList03")

def dur_usjnt_taboo_info(item_seq:str) -> Dict[str, str]:
    """ 병용금기 정보 조회 
    res ex: 201405281
    {
        "DUR_SEQ": "19",
        "TYPE_CODE": "A",
        "TYPE_NAME": "병용금기",
        "MIX": "단일",
        "INGR_CODE": "D000762",
        "INGR_KOR_NAME": "이트라코나졸",
        "INGR_ENG_NAME": "Itraconazole",
        "MIX_INGR": null,
        "ITEM_SEQ": "201405281",
        "ITEM_NAME": "씨코나졸정(이트라코나졸)",
        "ENTP_NAME": "(주)씨엠지제약",
        "CHART": "흰색 또는 거의 흰색의 달걀형 필름코팅정",
        "FORM_CODE": "010201",
        "ETC_OTC_CODE": "02",
        "CLASS_CODE": "06290",
        "FORM_NAME": "필름코팅정",
        "ETC_OTC_NAME": "전문의약품",
        "CLASS_NAME": "기타의 화학요법제",
        "MAIN_INGR": "[M083734]이트라코나졸",
        "MIXTURE_DUR_SEQ": "19",
        "MIXTURE_MIX": "단일",
        "MIXTURE_INGR_CODE": "D000027",
        "MIXTURE_INGR_KOR_NAME": "심바스타틴",
        "MIXTURE_INGR_ENG_NAME": "Simvastatin",
        "MIXTURE_ITEM_SEQ": "200201767",
        "MIXTURE_ITEM_NAME": "콜레스틴정(심바스타틴)",
        "MIXTURE_ENTP_NAME": "대화제약(주)",
        "MIXTURE_FORM_CODE": "010201",
        "MIXTURE_ETC_OTC_CODE": "02",
        "MIXTURE_CLASS_CODE": "02180",
        "MIXTURE_FORM_NAME": "필름코팅정",
        "MIXTURE_ETC_OTC_NAME": "전문의약품",
        "MIXTURE_CLASS_NAME": "동맥경화용제",
        "MIXTURE_MAIN_INGR": "[M089710]심바스타틴",
        "NOTIFICATION_DATE": "20090303",
        "PROHBT_CONTENT": "횡문근융해증",
        "REMARK": null,
        "ITEM_PERMIT_DATE": "20141112",
        "MIXTURE_ITEM_PERMIT_DATE": "20021015",
        "MIXTURE_CHART": "황갈색의 원형필름코팅정",
        "CHANGE_DATE": "20230803",
        "MIXTURE_CHANGE_DATE": "20240416",
        "BIZRNO": "1348171976"
    }
    """
    return dur_info(item_seq, "getUsjntTabooInfoList03")

def dur_prdlst_info(item_seq:str) -> Dict[str, str]:
    """ DUR 품목정보 조회 
    res ex: 195700013
    {
        "ITEM_SEQ": "195700013",
        "ITEM_NAME": "제일에페드린염산염주사액4%",
        "ENTP_NAME": "(주)제일제약",
        "ITEM_PERMIT_DATE": "1957April26th",
        "ETC_OTC_CODE": "전문의약품",
        "CLASS_NO": "[222]진해거담제",
        "CHART": "무색 투명한 액이 든 갈색 투명한 앰플주사제",
        "BAR_CODE": "8806505004633",
        "MATERIAL_NAME": "에페드린염산염,,40,밀리그램,KP,",
        "EE_DOC_ID": "https://nedrug.mfds.go.kr/pbp/cmn/pdfViewer/195700013/EE",
        "UD_DOC_ID": "https://nedrug.mfds.go.kr/pbp/cmn/pdfViewer/195700013/UD",
        "NB_DOC_ID": "https://nedrug.mfds.go.kr/pbp/cmn/pdfViewer/195700013/NB",
        "INSERT_FILE": "http://www.health.kr/images/insert_pdf/In_A11A0490A0002_00.pdf",
        "STORAGE_METHOD": "차광한 밀봉용기, 실온(1～30℃)보관,",
        "VALID_TERM": "제조일로부터 36개월",
        "REEXAM_TARGET": None,
        "REEXAM_DATE": None,
        "PACK_UNIT": None,
        "EDI_CODE": "650500461",
        "CANCEL_DATE": None,
        "CANCEL_NAME": "정상",
        "TYPE_CODE": "C",
        "TYPE_NAME": "임부금기",
        "CHANGE_DATE": "2018June14th",
        "BIZRNO": "5148126323"
    }
    """
    return dur_info(item_seq, "getDurPrdlstInfoList03")

def dur_SpcifyAgrdeTaboo_info(item_seq:str) -> Dict[str, str]:
    """ 특정연령금기 정보 조회 
    res ex:
    {
        "TYPE_NAME": "특정연령대금기",
        "MIX_TYPE": "단일",
        "INGR_CODE": "D000064",
        "INGR_ENG_NAME": "Tetracycline Hydrochloride",
        "INGR_NAME": "테트라사이클린염산염",
        "MIX_INGR": null,
        "FORM_NAME": "경질캡슐제, 산제",
        "ITEM_SEQ": "196000001",
        "ITEM_NAME": "테라싸이클린캅셀250밀리그람(염산테트라싸이클린)",
        "ITEM_PERMIT_DATE": "19600614",
        "ENTP_NAME": "(주)종근당",
        "CHART": "황색의 결정 또는 결정성 가루가 들어 있는 상부는 갈색, 하부는 담회색의 캅셀이다.",
        "CLASS_CODE": "06150",
        "CLASS_NAME": "주로 그람양성, 음성균, 리케치아, 비루스에 작용하는 것",
        "ETC_OTC_NAME": "전문의약품",
        "MAIN_INGR": "[M223235]테트라사이클린염산염",
        "NOTIFICATION_DATE": "20140109",
        "PROHBT_CONTENT": "소아 등(특히 치아 형성기인 12세 미만의 소아)에 투여 시, 치아의 착색？법랑질 형성 부전, 또는 일과성 골발육 부전을 일으킬 수 있음",
        "REMARK": "다만, 다른 약을 사용할 수 없거나 효과가 없는 경우에만 8세 이상 신중투여",
        "INGR_ENG_NAME_FULL": "Tetracycline Hydrochloride(테트라사이클린염산염)",
        "CHANGE_DATE": "20200313"
    }
    """
    return dur_info(item_seq, "getSpcifyAgrdeTabooInfoList03")

def dur_CpctyAtent_info(item_seq:str) -> Dict[str, str]:
    """ 용량주의 정보 조회 
    res ex: 196000011
    {
        'DUR_SEQ': '2773',
        'EFFECT_NAME': '호흡기관용약',
        'TYPE_NAME': '효능군중복',
        'INGR_CODE': 'D000893',
        'INGR_NAME': '클로르페니라민말레산염',
        'INGR_ENG_NAME': 'Chlorpheniramine Maleate',
        'FORM_CODE_NAME': '나정',
        'MIX': '단일',
        'MIX_INGR': None,
        'ITEM_SEQ': '196000011',
        'ITEM_NAME': '페니라민정(클로르페니라민말레산염)',
        'ITEM_PERMIT_DATE': '19601010',
        'CHART': '미황색의 원형 정제',
        'ENTP_NAME': '(주)유한양행',
        'FORM_CODE': '010101',
        'FORM_NAME': '나정',
        'ETC_OTC_CODE': '01',
        'ETC_OTC_NAME': '일반의약품',
        'CLASS_CODE': '01410',
        'CLASS_NAME': '항히스타민제',
        'MAIN_INGR': '[M223211]클로르페니라민말레산염',
        'NOTIFICATION_DATE': '20131227',
        'PROHBT_CONTENT': None,
        'REMARK': None,
        'INGR_ENG_NAME_FULL': 'Chlorpheniramine Maleate(클로르페니라민말레산염)',
        'CHANGE_DATE': '20190826',
        'BIZRNO': '1188100601',
        'SERS_NAME': '항히스타민제'
    }
    """
    return dur_info(item_seq, "getCpctyAtentInfoList03")

def dur_mdctnPdAtent_info(item_seq:str) -> Dict[str, str]:
    """ 투여기간주의 정보 조회 """
    return dur_info(item_seq, "getMdctnPdAtentInfoList03")

def dur_EfcyDplct_info(item_seq:str) -> Dict[str, str]:
    """ 효능교차 정보 조회 
    res ex: 198400314
    {
        "DUR_SEQ": "2600",
        "EFFECT_NAME": "정신신경용제",
        "TYPE_NAME": "효능군중복",
        "INGR_CODE": "D000468",
        "INGR_NAME": "오르페나드린염산염",
        "INGR_ENG_NAME": "Orphenadrine Hydrochloride",
        "FORM_CODE_NAME": "나정",
        "MIX": "단일",
        "MIX_INGR": None,
        "ITEM_SEQ": "198400314",
        "ITEM_NAME": "닉신정(오르페나드린염산염)(수출용)",
        "ITEM_PERMIT_DATE": "19841019",
        "CHART": "백색의 원형정제이다.",
        "ENTP_NAME": "아주약품(주)",
        "FORM_CODE": "010101",
        "FORM_NAME": "나정",
        "ETC_OTC_CODE": "02",
        "ETC_OTC_NAME": "전문의약품",
        "CLASS_CODE": "01190",
        "CLASS_NAME": "기타의 중추신경용약",
        "MAIN_INGR": "[M222877]오르페나드린염산염",
        "NOTIFICATION_DATE": "20131227",
        "PROHBT_CONTENT": None,
        "REMARK": None,
        "INGR_ENG_NAME_FULL": "Orphenadrine Hydrochloride(오르페나드린염산염)",
        "CHANGE_DATE": "20131231",
        "BIZRNO": "1138106691",
        "SERS_NAME": "항콜린성 항파킨슨제"
    }
    """
    return dur_info(item_seq, "getEfcyDplctInfoList03")

def dur_seobangjeong_partitn_atent_info(item_seq:str) -> Dict[str, str]:
    """ 서방정분할주의 정보 조회 
    res ex: 197100081
    {
        'TYPE_NAME': '분할주의',
        'ITEM_SEQ': '197100081',
        'ITEM_NAME': '키모랄에스정',
        'ITEM_PERMIT_DATE': '1971May6th',
        'FORM_CODE_NAME': '장용성필름코팅정',
        'ENTP_NAME': '(주)에이프로젠바이오로직스',
        'CHART': '내수용 : 연녹색의 원형 장용성 필름코팅정, 수출용 : 적색의 원형 장용성 필름코팅정',
        'CLASS_CODE': '03950 ',
        'CLASS_NAME': '효소제제',
        'ETC_OTC_NAME': '일반의약품',
        'MIX': '복합',
        'MAIN_INGR': '[M051649]결정트립신/[M095415]브로멜라인/[M095415]브로멜라인/[M051649]결정트립신',
        'PROHBT_CONTENT': '분할불가',
        'REMARK': None,
        'CHANGE_DATE': '20210629',
        'BIZRNO': '2188100518'
    }
    """
    return dur_info(item_seq, "getSeobangjeongPartitnAtentInfoList03")

def dur_pwnm_taboo_info(item_seq:str) -> Dict[str, str]:
    """ 임부금기 정보 조회 
    res ex: 197600065
    {
        'TYPE_NAME': '임부금기',
        'MIX_TYPE': '단일',
        'INGR_CODE': 'D000732',
        'INGR_ENG_NAME': 'Cyclophosphamide',
        'INGR_NAME': '시클로포스파미드',
        'MIX_INGR': None,
        'FORM_NAME': '필름코팅정',
        'ITEM_SEQ': '197600065',
        'ITEM_NAME': '알키록산정(시클로포스파미드정)',
        'ITEM_PERMIT_DATE': '19760414',
        'ENTP_NAME': '제이더블유중외제약(주)',
        'CHART': '백색의 필름코팅정',
        'CLASS_CODE': '04210',
        'CLASS_NAME': '항악성종양제',
        'ETC_OTC_NAME': '전문의약품',
        'MAIN_INGR': '[M040333]시클로포스파미드',
        'NOTIFICATION_DATE': '20081211',
        'PROHBT_CONTENT': '동물실험에서 유전독성 및 태아손상 유발 가능성.',
        'REMARK': None,
        'INGR_ENG_NAME_FULL': 'Cyclophosphamide(시클로포스파미드)',
        'CHANGE_DATE': '20240507'
    }
    """
    return dur_info(item_seq, "getPwnmTabooInfoList03")

def dur_odsn_atent_info4(item_name:str) -> Dict[str, str]:
    """임부 금기 정보 """
    servicekey = apikeys.dur_odsn_atent_info4_service_key
    url = apikeys.dur_odsn_atent_info4_url
    params = {
        "serviceKey": servicekey,
        "pageNo": 1,
        "numOfRows": 10,
        "itemName": item_name,
        "type": "json"
    }
    res = requests.get(url, params=params)
    if res.status_code != 200: # 정상 응답이 아닌 경우
        return {}
    data = res.json()
    items = data['body']
    if items.get('totalCount', 0) == 0:
        return {}
    return items['items'][0] # 여러개 응답중 첫 번째 항목만 반환


def find_usjnt_taboo(item_seqs:List[str]) -> List[str]:
    """ 서로 다른 약품의 병용금기 정보 조회 """
    nsjnt_taboo_dict = defaultdict(set)
    for item_seq in item_seqs:
        taboo_list = dur_usjnt_taboo_info(item_seq)
        if taboo_list:
            for taboo in taboo_list:
                nsjnt_taboo_dict[item_seq].add(taboo['MIXTURE_ITEM_SEQ'])
    
    res = []
    for first in item_seqs:
        for second in item_seqs:
            if first == second:
                continue
            if second in nsjnt_taboo_dict[first]:
                res.append((first, second))
    return res


def name_list_to_data(name_list:List[str]) -> Dict[str, str]:
    name_item_seqs = []
    for name in name_list:
        item_seqs = item_seq_list(name)
        name_item_seqs.extend([ [name, item_seq] for item_seq in item_seqs ])
    print(name_item_seqs)
    item_seqs = [ item_seq for _, item_seq in name_item_seqs ]
    # 최종적으로 이름별 약물 정보를 포함한 딕셔너리 반환
    pill = { item_seq: drug_info(name, item_seq) for name, item_seq in name_item_seqs }
    ret = {'pill': pill}
    ret['taboo'] = [ [pill[a]['약이름'], pill[b]['약이름']] for a, b in find_usjnt_taboo(item_seqs)]
    return ret


def what_is_this_pill(image_path:str) -> Dict[str, str]:
    """메인 로직"""
    # 이미지에서 감지된 약물 이름 목록을 가져와서 각 약물의 정보를 저장
    # 약물 이름별로 ITEM_SEQ 리스트를 가져오고, 각 ITEM_SEQ에 대해 상세 정보 수집
    name_list = predict(image_path)
    name_list = [name.replace("mg", "밀리그램") for name in name_list]
    return name_list_to_data(name_list)


def clean_data(image_path):
    if image_path == None:
        return {}, []
    else:
        full_data = what_is_this_pill(image_path)
        pill_data = full_data['pill']
        return pill_data, full_data['taboo']

def show_ui():
    senior_css = """
    p.info {
        font-size: 170%;
        font-weight: bolder;
        text-align: center;
    }
    p.subhead {
        font-size: 170%;
        font-weight: 600;
    }
    p.pill_name {
        font-size: 185%;
        font-weihgt: bolder;
    }
    p.pill_info {
        font-size: 150%;
        line-hegiht: 1.6;
    }
    p.warn {
        font-size: 185%;
        color: red;
        font-weight: bolder;
        text-align: center;
    }
    p.alert {
        font-size: 130%;
        font-weight: bolder;
        text-align: center;
    }
    .info_button{
        font-size: 170%;
    }
    """
    
    # Gradio 인터페이스 설정
    # 이미지 파일 경로를 입력으로 받고, JSON 형식으로 약물 정보를 출력
    with gr.Blocks(css=senior_css) as demo:#theme=theme_moyak
        gr.Markdown(f"<p class='alert'>이 서비스는 식품의약품안전처와 약학정보원이 제공하는 데이터를 기반으로 제작하였습니다. 참고용으로만 사용하고 반드시 약사 및 의사와 상담 후 복용하시기 바랍니다.</p>")
        gr.Image(value=Image.open("./image/header.png"), show_label=False, interactive=False)
        
        pill_infos = gr.State({})
        taboo_infos = gr.State([])
        
        gr.Markdown(f"<p class='info'>약을 흰색 배경위에 올려서 찍어주세요.</p>\n<p class='info'>(약에 글씨나 그림이 있다면 잘 보이게 찍어주세요.)</p>")
        input_image = gr.Image(type="filepath")
        
        pill_info_button = gr.Button("정보", elem_classes="info_button")

        @gr.render(inputs=[taboo_infos])
        def render_taboo_components(taboo_infos):
            # 병용금기 정보
            if taboo_infos:
                gr.Markdown("---")
                #gr.Markdown(f"<p class='subhead'>병용금기 정보</p>")
                gr.Markdown(f"<p class='info'>이 약은 같은 기간에 함께 드시면 위험할 수 있습니다. 복용에 주의해주세요.</p>")
            for a, b in taboo_infos:
                gr.Markdown(f"<p class='warn'>{a} - {b}</p>")
        
        @gr.render(inputs=[pill_infos])
        def render_pills_components(pill_infos):
            if len(pill_infos) != 0:
                gr.Markdown("---")
                gr.Markdown("<p class='info'>복용약 목록</p>")
            # 약품 정보
            for pill in pill_infos.values():
                for k, v in pill.items():
                    gr.Markdown(f"<p class='subhead'>{k}</p>")
                    if isinstance(v, (list, tuple)):
                        for item in v:
                            gr.Markdown(f"<p class='pill_info'>{item}</p>")
                    else:
                        if k == '약이름':
                            gr.Markdown(f"<p class = 'pill_name'>{v}</p>")
                        elif k == '효능':
                            gr.Markdown(f"<p class = 'pill_info'>{v}</p>")
                        elif k == '이미지':
                            gr.Markdown(v)
                gr.Markdown("---") 
            
        pill_info_button.click(
            fn=clean_data,
            inputs=[input_image],
            outputs=[pill_infos, taboo_infos]
        )

    demo.launch()

if __name__ == "__main__":
    show_ui()

    # name_seqs = [["심비타정20밀리그램", "202002293"], ["씨코나졸정", "201405281"], ["페니라민주사", "196000010"]]
    # name_list = ['심바코틴정', '씨코나졸정', '웰러드연질캡슐', '엘바스타정', '로바타딘정', '휴메트린정']
    # res = name_list_to_data(name_list)
    # print(res)


