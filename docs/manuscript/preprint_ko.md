# 근거 인용에 기반한 충실한 LLM 체세포 변이 해석
(Citation-grounded retrieval for faithful LLM somatic variant interpretation)

**저자:** Ka-Kyung Kim (김가경)

**소속:** Independent Researcher, Seoul, Republic of Korea

**교신:** kakyung.kim@gmail.com

---

## 초록

**목적(Objective).** 대규모 언어모델(large language models, LLM)은 체세포 변이 해석 초안을 작성할 수 있으나, 임상 활용을 가로막는 두 가지 실패 양상을 보인다. 근거 인용을 조작(fabricate)하며, 감사 가능한(auditable) 근거가 아니라 잘 알려진 변이에 대한 파라메트릭 기억(parametric memory)에 의존한다는 점이다. 본 연구는 검색 정초(retrieval grounding)가 LLM 해석을 충실하고 감사 가능하게 만들 수 있는지, 그리고 정확도 효과가 실재하는지 아니면 누출(leakage) 산물인지를 물었다.

**방법(Materials and Methods).** 두 국제 표준 — ClinGen/CGC/VICC oncogenicity와 AMP/ASCO/CAP 임상 tier — 위에서 변이를 분류하는 이중 모드 체세포 변이 해석기를 구축하였다. 시스템은 하이브리드 인용 근거 기반 검색(구조화된 지식베이스, CIViC 근거 진술에 대한 밀집 검색(dense retrieval), 지식 그래프)을 사용하며, 모든 주장이 검색된 식별자를 인용하고 변이 특이적 근거가 없을 때 판단을 보류(abstain, VUS 지정)하도록 요구하는 충실성 계약(faithfulness contract) 하에 작동한다. **생성(Generative) 모드**(LLM이 라벨을 부여)를 **결정론적(Deterministic) 모드**(방향성 인식 규칙이 라벨을 부여하고 LLM은 설명만 작성)와, 그리고 무검색 기준선과 비교하였다. 56개 변이, 5개 암종 TCGA 코호트와 외부의 균형 잡힌 70개 변이 전문가 골드 스탠다드(Horak et al. 2022)에서, 누출 없는 충실성 지표, 누출 통제(시간적 홀드아웃, 자기 근거 제외, 두 번째 모델, 임베딩 제거 실험), 부트스트랩 신뢰구간, 정확(exact) McNemar 검정으로 평가하였다.

**결과(Results).** 검색을 사용하면 인용 조작이 0%(무검색 46.4%, 95% CI 33.9–58.9%)였고, 완전한 인용 근거화·방향성 충실성·보류 재현율을 보였다. 검색은 자신만만하게 과대 판정된 56개 중 12개(21.4%) 변이를 근거 정초 VUS로 재분류했다. 균형 잡힌 골드 스탠다드에서 3분류 정확도는 우월이 아니라 비열등했다(검색 0.600, 무검색 0.586, 규칙 0.557; McNemar p = 1.0 및 0.61). 시간적 홀드아웃, 자기 근거 제외, 두 번째 모델, 임베딩 통제는 정확도를 통계적으로 변화시키지 않았으며, 이는 결과가 검색 코퍼스 누출에 의해 추동되지 않음을 시사한다.

**고찰(Discussion).** 검색 정초는 LLM 변이 해석을 충실하고 감사 가능하게 만들며 파라메트릭 과대 판정을 억제하지만, 이 규모에서는 분류 정확도를 향상시키지 않는다.

**결론(Conclusion).** 임상 의사결정 지원의 전제 조건인 충실성과 감사가능성은 구조적으로 보장될 수 있다. 정확도 이득을 확립하려면 더 크고 검정력 있으며 누출 통제된 전문가 판정 벤치마크가 필요하며, 본 연구는 그 설계를 제시한다.

**키워드:** 체세포 변이 해석; 대규모 언어모델; 검색 증강 생성; 충실성; 감사가능성; 임상 의사결정 지원; 정밀 종양학.

---

## 배경 및 의의

체세포 변이 해석 — 종양 변이가 oncogenic하고 임상적으로 실행 가능(actionable)한지 판단하는 일 — 은 정밀 종양학의 율속 단계다. 분자종양위원회(molecular tumour board)에서 각 분류는 표적 치료와 임상시험 등록을 지시하거나 보류하며, 임상 보고서에 들어가는 모든 주장은 감사·책임·규제 검토를 위해 1차 출처로 추적 가능해야 한다. 이 과제는 인력 병목이기도 하다. 전문가 큐레이션은 일상적 종양 시퀀싱의 변이 물량을 따라가지 못하며, 도움이 가장 필요한 희귀하거나 큐레이션이 부족한 변이가 판정이 가장 느리고 불확실하다. 따라서 정확하면서 감사 가능한 보조 도구는 직접적 임상 가치를 가질 것이나, 그 출력이 한 줄 한 줄 신뢰될 수 있을 때에만 그러하다.

두 커뮤니티 표준이 이 과제를 구조화한다. ClinGen/CGC/VICC 프레임워크는 **oncogenicity**를 다섯 라벨 점수 기반 시스템(Oncogenic, Likely Oncogenic, VUS, Likely Benign, Benign)으로 정의하고 [1], AMP/ASCO/CAP 프레임워크는 **임상 tier**(Tier I–IV, 근거 수준 A–D)를 정의한다 [2]. 어느 표준이든 적용하려면 이질적 근거 — 큐레이션된 임상 주장, 약물–유전자 상호작용, 계산적 병원성 예측, 임상시험 현황 — 를 변호 가능하고 인용 가능한 판단으로 종합해야 한다.

이미 성숙한 생태계가 이 표준들을 운용한다. OncoKB [3], COSMIC [4], 크라우드소싱 CIViC [5] 같은 전문가 큐레이션 지식베이스는 변이 및 유전자 수준 임상 주장을 제공하며, CancerVar [6], Cancer Genome Interpreter [7], Personal Cancer Genome Reporter [8] 같은 규칙·모델 기반 플랫폼은 변이를 tier와 oncogenicity 판정에 매핑한다. 이 시스템들은 정확하고 감사 가능하지만 손으로 구축한 규칙 엔진과 사전 계산된 조회에 의존한다. 즉 자유 텍스트 근거를 즉석에서 읽지도, 자연어 정당화를 생성하지도 않으며, 희귀하거나 큐레이션이 부족한 변이 커버리지는 기반 데이터베이스에 의해 제한된다. 본 연구는 이 선행 연구를 우리 시스템이 양립해야 할 기존 기술로 취급하며 — 우리의 결정론적 모드는 같은 전통을 의도적으로 단순화하여 방향성을 인식하도록(direction-aware) 재구현한 것이다 — 우리가 능가한다고 주장하는 기준선으로 보지 않는다. 직교적으로, 계산적 변이 효과 예측기 AlphaMissense [9], 단백질 언어모델 ESM1b [10], 진화 모델 EVE [11] 는 유전체 규모의 병원성 사전 확률을 제공한다. 본 연구는 AlphaMissense를 하나의 근거 축으로 사용하되, 이러한 점수를 그 자체로는 임상적 실행 가능성을 확립할 수 없는 유전자 비특이적 사전 확률로 취급한다.

LLM은 자유 텍스트를 유창하게 읽고 구조화된 산문을 생성하므로 이러한 종합에 매력적이다. 그러나 두 실패 양상이 감사 가능한 임상 환경에서 순진한 사용을 안전하지 않게 만든다. 첫째, **인용 환각(hallucinated citations)**: 분류 정당화를 요청받은 LLM은 그럴듯하지만 존재하지 않는 PMID나 데이터베이스 식별자를 거리낌 없이 생성한다. 임상 보고서에서 조작된 참고문헌은 환자 안전 및 법적 위해 요인인데, 그것이 뒷받침하는 듯한 주장을 확인할 수 없기 때문이다. 둘째, **파라메트릭 누출(parametric leakage)**: 유명한 driver 변이(예: BRAF V600E, KRAS G12D)가 사전학습 데이터에 과다 표현되어 있어, LLM은 제공된 근거가 아니라 기억에서 교과서적 답을 재현할 수 있다. 이는 잘 알려진 변이의 외견상 정확도를 부풀리는 동시에, 표면적으로 유사하지만 기능적으로 benign한 변이에 자신만만한 과대 판정을 낳으며 — 실제로 benign 변이를 oncogenic으로 과대 판정하면 부적절한 표적 치료를 촉발할 수 있다.

검색 증강 생성(retrieval-augmented generation, RAG)은 자연스러운 완화책이다. 모델을 검색된 근거에 정초시키고 그 근거를 인용하도록 요구하는 것이다. 두 실패 양상 모두 유전체학 밖에서 잘 기록되어 있다. Gao et al. [12]의 ALCE 벤치마크는 인용 정밀도·재현율의 자동 평가를 정형화하고 강력한 LLM조차 자신의 주장을 빈번히 뒷받침하지 못함을 보였으며, Xiong et al. [13]의 MedRAG/MIRAGE 연구는 의학 질의응답에서 환각과 오래된 지식의 부분적 완화책으로 검색을 확립했다. 임상 유전체학 영역에서도 최근 연구가 LLM과 검색을 변이 해석에 적용하기 시작했다. Lin et al. [14]은 암 변이 분류에서 GPT-4o, Llama 3.1, Qwen 2.5를 벤치마킹하여 변이를 더 높은 근거 수준으로 과대 분류하는 체계적 경향 — 우리가 관찰한 것과 동일한 파라메트릭 과대 판정 — 을 보고하면서 검색과 프롬프트 엔지니어링이 도움이 되었음을 언급했고, Lu와 Cosgun [15]은 약 1억 9천만 개 변이 주석을 RAG와 미세조정으로 GPT-4o에 통합하여 높은 필드 수준 주석 정확도를 보고했다. 그러나 이 연구들은 전문가 라벨 대비 정확도를 강조하면서 두 질문을 충분히 검토하지 않았다. 첫째, **시스템이 실제로 충실한가** — 검색된 근거만 인용하고 근거가 없을 때 정직하게 보류하는가 — 그리고 일반 도메인 귀속 벤치마크 [12]가 하듯 외부 정답 키 없이 충실성을 측정할 수 있는가(유전체학 RAG 연구 [14,15]는 하지 않는다)? 둘째, **외견상의 정확도 이득이 실재하는가 아니면 누출 산물인가** — 시스템이 최근의 정답 진술 근거를 검색하여(코퍼스 누출) 또는 파라메트릭 회상으로(모델 누출) 성공하는가, 아니면 진정한 근거 정초 추론으로 성공하는가? 우리가 아는 한, 어떤 선행 변이 해석 연구도 누출 통제(시간적 홀드아웃 및 자기 근거 제외)된 정확도 평가를 누출 없는 충실성 감사와 함께 보고하지 않았으며, 이것이 본 연구가 겨냥하는 공백이다.

## 목적

본 연구는 응용 시스템과, 더 중심적으로는 헤드라인 정확도가 아니라 충실성과 누출을 중심에 둔 엄밀한 평가로 그 공백을 다룬다. 우리는 의도적인 통계적 절제를 가지고 세 주장을 제시한다. 첫째, 시스템은 **구조적으로 그리고 경험적으로 충실하다** — 인용 조작 0건, 완전한 근거화·보류로, 동일한 무검색 LLM이 갖지 못하는 속성이며 그 격차는 크고 통계적으로 견고하다. 둘째, 검색은 **자신만만한 파라메트릭 과대 판정을 억제한다** — 변이 특이적 근거를 읽음으로써 과대 판정된 여러 변이를 VUS로 재분류한다(각 재분류의 정답 여부는 전문가 판정을 기다린다). 셋째, 균형 잡힌 전문가 골드 스탠다드에서 검색은 정확도 면에서 **우월이 아니라 비열등하다**; n = 70에서 차이가 유의하지 않으므로 우리는 명시적으로 정확도 이득을 주장하지 않는다. 이어서 이 거동을 여러 누출 통제에 부쳐 그것이 단일 구성의 산물이 아니라 견고함을 보인다. 본 연구의 기여는 새로운 모델링 방법이나 기존 해석 플랫폼에 대한 정확도 향상이 아니라 응용적이고 평가적이다 — 구조적으로 충실한 시스템과 누출을 고려한 충실성/정확도 평가다.

---

## 방법

그림 1은 시스템을 요약한다. 하이브리드 검색 계층이 인용 가능한 근거 번들을 구성하여 충실성 계약 하의 두 해석 모드에 공급하고, 그 결과는 의사결정 지원 인터페이스로 표출된다.

![시스템 개요: 인용 근거 기반 검색을 갖춘 이중 모드 체세포 변이 해석](figures/F0_architecture.png)

**그림 1. 시스템 개요.** 각 변이는 하이브리드 인용 근거 기반 검색 계층(구조화·밀집·그래프 축)을 거쳐, 모든 항목이 인용 가능한 식별자를 지닌 근거 번들로 변환된다. 충실성 계약은 모든 주장이 검색된 식별자만 인용하고 변이 특이적 근거가 없을 때 보류(VUS 지정)하도록 요구한다. **생성(Generative) 모드**는 LLM이 근거로부터 oncogenicity와 tier 라벨을 직접 부여하고(자기일관성 투표와 에이전트형 검증기 포함), **결정론적(Deterministic) 모드**는 방향성 인식 규칙이 라벨을 부여하며 LLM은 근거 서술만 작성한다. 출력은 감사 가능한 의사결정 지원 인터페이스로 표출된다.

### 분류 표준

변이는 각각 통제된 열거형(enumeration)으로 강제된 두 축에서 분류되었다. **Oncogenicity**는 다섯 라벨(Oncogenic, Likely Oncogenic, VUS, Likely Benign, Benign)을 갖는 ClinGen/CGC/VICC 2022 점수 기반 표준을 따랐다. **임상 tier**는 AMP/ASCO/CAP 2017 표준(Tier I–IV, Tier I/II에 근거 수준 A–D)을 따랐다. ACMG/AMP 2015 생식세포 프레임워크는 과제가 체세포이므로 의도적으로 사용하지 않았다. 두 어휘를 enum으로 통일함으로써 생성 모드와 결정론적 모드를 동일한 라벨 공간에서 비교할 수 있었다.

### 데이터셋

**코호트(입력 변이).** 환자 변이는 cBioPortal REST API(TCGA PanCancer Atlas, 공개)에서 서사적 대비를 위해 선택된 다섯 암종 — 폐선암(NSCLC), 유방암, 대장암, 피부 흑색종, 췌장암 — 에 걸쳐 각 7개 샘플(35개 샘플)로 추출되었다. 선택은 27개 유전자 driver 패널로 제한되고 결정론적이었으며, BRAF V600E 같은 쇼케이스 변이가 흑색종과 대장암 샘플 모두에 등장하도록 보장하여 맥락 의존성 분석을 가능케 했다. (유전자, 단백질 변화, 암종)으로 중복 제거하고 단계적으로 선택한 후 **56개 변이×맥락 단위**가 분류되었다(398개 고유 후보 중).

**지식 출처(근거 계층).** 오프라인 스냅샷은 CIViC(1,714개 패널 근거 행; CC0), DGIdb(27개 유전자에 걸친 2,608개 유전자–약물 상호작용), Ensembl VEP REST를 통한 AlphaMissense(352개 missense SNV에 대한 계산적 병원성, VICC 계산 코드로 매핑), ClinicalTrials.gov v2(37개 임상시험)로부터 구성되었다. CIViC 근거 진술은 검색을 위해 영속적 밀집 인덱스에 임베딩되었다.

**외부 벤치마크(정답).** 외부 골드 스탠다드는 ClinGen/CGC/VICC oncogenicity 표준화 논문인 Horak et al. (2022)의 Supplemental Table 3 — 9개 유전자(FLT3, BRAF, IDH1, KRAS, PIK3CA, PTEN, RB1, EZH2, TP53)에 걸친 70개 전문가 분류 체세포 변이 — 였다. 결정적으로 라벨 분포가 균형(VUS 30, Likely Oncogenic 19, Oncogenic 14, Benign 5, Likely Benign 2)되어 있어, 단일 클래스로 심하게 치우친 CIViC 임상 주장과 달리 변별력 있는 벤치마크가 된다. Horak 라벨은 재분배되지 않았고 파생 지표만 보고된다.

### 하이브리드 인용 근거 기반 검색

각 변이에 대해 세 축에서 근거 번들이 구성되었으며, 모든 항목은 인용 가능한 식별자를 지녔다. **구조화** 축은 CIViC에서 유전자 + 단백질 변화의 정확 조회, DGIdb에서 유전자 수준 약물 조회, 유전체 좌표에 의한 AlphaMissense 조회(VICC 계산 코드 산출)를 수행했다. **밀집(dense)** 축은 CIViC 진술에 대해 도메인 임베딩(기본값 NeuML/PubMedBERT; 제거 실험으로 OpenAI text-embedding-3-small)을 사용하고, BM25와 Chroma 검색을 상호 순위 융합(Reciprocal Rank Fusion)으로 융합했으며, 동일 유전자 주제 표류를 방지하기 위해 동일 변이 적중만 부착했다. **그래프** 축은 networkx 지식 그래프(유전자·변이·질환·약물·임상시험)를 사용해 공유 약물을 통해 관련 변이를 드러냈다. 출력을 지배한 **충실성 계약**은 다음과 같다: 분류는 검색된 식별자만 인용할 수 있고, 변이 특이적 근거가 없을 때 시스템은 보류(VUS 지정)해야 했다(유전자 수준의 약물 적용 가능성은 변이 특이적 근거로 인정되지 않았다).

### 이중 모드 분류: 생성 모드와 결정론적 모드

두 모드는 유연성과 재현성 사이의 의도적 절충을 구현하며, 시스템은 모든 변이에 대해 둘을 함께 실행한다. **생성(Generative) 모드**는 LLM이 직접 라벨을 결정하게 한다: 언어모델은 어떤 고정 규칙도 열거하지 못하는 자유 텍스트 근거를 읽고 가중할 수 있으므로, 이 모드는 탐색적 해석과 희귀하거나 큐레이션이 부족한 변이에 적합하나 실행 간 변동성과 과대 판정 경향을 대가로 한다. 반면 **결정론적(Deterministic) 모드**는 투명하고 방향성을 인식하는 규칙으로 라벨을 고정하고 LLM을 사람이 읽을 수 있는 근거 서술 작성으로만 강등한다; 이는 재현성과 감사가능성 — 매 실행마다 동일한 출력, 큐레이션된 규칙 엔진의 전통 — 을 사면서도 유창한 자연어 정당화를 얻고, 모델의 파라메트릭 사전 확률이 근거를 압도하지 못하게 한다. 동일한 변이에 둘을 모두 실행하는 것 자체가 유의미하다: 유연한 독해자와 고정된 규칙이 불일치하는 지점이 진정한 해석적 불확실성을 국소화하므로(3.5절), 불일치는 결함이 아니라 신호로 취급된다.

**생성(Generative) 모드.** LLM(gpt-4o-mini)이 enum 어휘로 제한되고 근거 번들에 정초된 상태로 oncogenicity와 tier 라벨을 직접 부여했다. 자기일관성 투표(n = 3; 합의를 신뢰도 점수로 매핑)와 에이전트형 검증기(과대 주장을 하향 판정하는 적대적 2차 통과로, 보류 시 건너뜀)로 강화되었다. **결정론적(Deterministic) 모드.** 방향성 인식 규칙이 CIViC 유의성과 방향으로부터 라벨을 부여했다(따라서 "Unaltered Function" 또는 "Does Not Support" 근거는 oncogenicity에 반하여 계산되고, Sensitivity/Response 근거만 실행 가능성을 부여한다); 여기서 LLM은 자연어 근거 서술만 작성했다. **무검색 기준선**은 근거 번들을 제거한 생성 모드 프롬프트를 실행하여 파라메트릭 거동을 분리했다.

우리는 **gpt-4o-mini**를 의도적으로 주모델로 사용했다: 본 연구의 기여는 특정 모델이 아니라 검색·충실성 아키텍처이며, 저렴한 모델은 코호트 규모의 이중 모드 실행과 제거 실험을 감당 가능하게 만들고 보수적인 능력 하한을 설정한다 — 약한 모델에서 입증된 속성은 더 강한 모델에서도 성립할 가능성이 높다. **온도 0**은 결정성과 재현성을 위해 사용했으며, 투표에 필요한 답의 다양성을 유도하기 위해 **자기일관성 투표 통과에만 0.4**를 사용했다. 발견이 모델 크기의 산물이 아님을 확인하기 위해 더 강한 **gpt-4o**로 외부 벤치마크를 복제했고(3.4절, 표 1), 다른 독점 또는 공개 모델을 광범위하게 스윕하지는 않았으며 이를 한계로 명시한다.

### 평가 및 통계

세 부류의 평가가 수행되었다. **누출 없는 충실성 지표**는 외부 정답을 필요로 하지 않았다: 환각 인용률(생성된 인용이 검색 번들에 없는 변이의 비율), 인용 근거화, 방향성 충실성(부여된 라벨이 인용 근거의 방향을 존중하는가), 보류 재현율(근거 없는 변이 중 올바르게 보류된 비율), 모드 간 Cohen's κ. **제거 실험(ablation)**은 결정론적 모드, 무검색 LLM, 검색을 갖춘 생성 모드를 비교했다. **외부 벤치마크**는 Horak 골드 스탠다드에 대해 5분류 및 축약 3분류 정확도와 κ를 계산했다. 누출 통제는 **시간적 분할**(검색 코퍼스를 컷오프 연도 이전 문헌으로 제한), **자기 근거 제외(leave-own-evidence-out, LOVO)** 제거 실험(검색 전에 각 변이 자체의 큐레이션 CIViC 근거 제거), **두 번째 모델** 복제(gpt-4o), **임베딩 제거 실험**(PubMedBERT 대 MiniLM 대 OpenAI, 보류된 자기 근거의 recall@5로 채점)으로 구성되었다. 여덟 가지 추가 코호트 분석(암종 간 일관성, 민감성/내성, 밀집 검색 회수 향상, AlphaMissense–LLM 일치, 보정, 불일치 집중, hotspot 대 희귀, 검증기 순효과)이 거동을 특성화했다.

불확실성은 정확도와 일치도에 대한 비모수 부트스트랩 95% 신뢰구간으로 정량화되었고, 쌍을 이룬 방법들은 변이별 정확성에 대한 정확 McNemar 검정으로 비교되었다; 보고된 모든 p값은 양측 검정이다. 구현은 파이프라인과 90개 단위 테스트로 구성되었으며, 시스템은 재현성을 위해 커밋된 스냅샷에서 오프라인으로 실행된다.

### 의사결정 지원 인터페이스

충실한 해석을 의사결정 시점에 사용 가능하게 만들기 위해, 시스템은 브라우저 대시보드를 제공한다. 코호트 탐색기는 근거 상태, 약물 또는 임상시험 가용성, 모드 간 불일치로 변이를 필터링하고 필터링된 집합을 내보낸다. 변이별 보기는 생성 모드와 결정론적 모드의 판정을 나란히 보여주며, 인용된 각 항목은 1차 출처로 가는 클릭 가능한 링크로 렌더링된다 — CIViC 근거 항목, ClinicalTrials.gov 기록, 외부 지식베이스(OncoKB, ClinVar, cBioPortal, COSMIC, DGIdb). 근거 정초 질의응답 채팅은 충실성 계약을 자유 텍스트 상호작용으로 확장한다: 선택된 변이에 대한 질문에 그 변이의 검색 번들로부터만 답하고, 번들이 질문을 다루지 못할 때는 보류("I cannot answer from the available evidence")하며 유전자 수준의 약물 적용 가능성을 불충분한 것으로 취급한다(그림 8). 이 인터페이스는 연구·교육용 데모이며 검증된 임상 도구가 아니다.

---

## 결과

### 충실성(누출 없음) — 헤드라인 결과

충실성 계약 하에서 검색 시스템은 구조적으로도 경험적으로도 충실했다(그림 2). 56개 변이 코호트 전반에서 **환각 인용률은 0.0**(인용을 생성한 46개 변이 중 0개)이었고, **인용 근거화는 1.0**(44/44 근거화), **방향성 충실성은 1.0**(44/44 — 부여된 어떤 라벨도 인용 근거의 방향과 모순되지 않음), **보류 재현율은 1.0**(근거 없는 변이 10/10이 올바르게 VUS로 보류됨)이었다. 추가로 근거를 지닌 2개 변이도 보수적으로 보류되었으며, 이 보수성은 고찰에서 논의하는 VUS 과대 재분류와 연결된다. 근거화 및 방향성 분모가 46이 아니라 44인 이유는, 인용을 생성한 46개 변이 중 2개가 확인할 수 있는 해석 가능한 검색 식별자가 없는 인용 불가능한 토큰만 생성했기 때문이다. 생성 모드와 결정론적 모드 간 일치는 oncogenicity에서 상당했고(Cohen's κ = 0.713) tier에서 중간이었으며(κ = 0.417), 이는 두 모드가 oncogenic/benign 축보다는 주로 tier 경계에서 차이를 보임과 일치한다.

![인용 근거 기반 검색의 충실성](figures/F1_faithfulness.png)

**그림 2. 인용 근거 기반 검색의 충실성(코호트, n = 56).** 충실성 계약 하의 환각 인용률, 인용 근거화, 방향성 충실성, 보류 재현율; 오른쪽 분수는 근거 개수다. 근거를 지닌 2개 변이가 추가로 보수적으로 보류되었다.

### 제거 실험 — 검색이 기여하는 것

검색을 제거하면 충실성이 단지 저하되는 데 그치지 않고 소멸되었다(그림 3). 동일한 무검색 LLM은 **56개 변이 중 26개(46.4%, 95% CI 33.9–58.9%)에서 인용을 조작**했다 — 조작된 PMID("PMID: 12345678") 같은 자리표시자나 발명된 식별자, 근거 없는 데이터베이스 토큰을 생성 — 반면 검색 시스템은 하나도 조작하지 않았다(0%). 무검색 조작률의 95% CI가 0을 포함하지 않으므로 이 충실성 격차는 통계적으로 견고하며 본 연구에서 가장 강력한 정량적 발견이다.

![제거 실험: 검색은 인용 조작을 소거하고 파라메트릭 과대 판정을 억제한다](figures/F2_ablation.png)

**그림 3. 제거 실험.** (a) 무검색 LLM은 변이의 46.4%에서 인용을 조작(95% CI가 0을 배제)한 반면 검색은 0%였다. (b) 자신만만한 파라메트릭 과대 판정이 근거 정초 VUS로 재분류된 예(정답 여부는 전문가 판정 대기).

검색은 또한 **자신만만한 파라메트릭 과대 판정을 억제**했다. 총 56개 변이 중 12개(21.4%)가 무검색 모델에 의해 oncogenic 또는 likely oncogenic으로 판정되었으나 검색 시스템이 변이 특이적 근거를 읽은 후 VUS로 재분류되었다. 예를 들어 EGFR E114K는 무검색 Likely Oncogenic/Tier II에서 검색 시 VUS/Tier IV로, PTEN R130\*는 Oncogenic/Tier I에서 VUS/Tier III로, TP53 P152L은 Likely Oncogenic/Tier II에서 VUS/Tier IV로 이동했다. 이 열두 개 중 다수는 절단형(truncating), 프레임시프트, 스플라이스 부위 변이(예: APC R1450\*, CDKN2A R58\*, BRCA2 N1784Kfs\*3)로, 파라메트릭 모델은 자신만만한 driver 판정으로 기본 설정되었으나 검색 시스템은 변이 특이적 임상 근거를 찾지 못해 보류했다. 우리는 이 21.4%가 정답 여부가 아니라 행동 변화의 측정임을 강조한다: 검색 정초 VUS가 열두 개 모두에 대해 옳다는 보장은 없으며(종양억제 유전자의 일부 절단형 변이는 실제로 진정 oncogenic할 수 있다), 따라서 각 재분류가 과대 판정의 적절한 교정인지 과도하게 보수적인 하향 판정인지는 전문가 판정을 기다린다(고찰 참조). 여기서 주장하는 감사 가능한 속성은 단지 과신된 파라메트릭 판정이 근거 정초 보류로 대체된다는 것뿐이다. 무검색 모드와 검색 모드 간 tier 수준 일치는 그에 상응하여 낮았으며(Cohen's κ = 0.18), 두 축이 실질적으로 다르게 거동함을 확인했다. 요약하면, 검색은 인용 환각을 소거하고 자신만만한 파라메트릭 과대 판정을 억제한다; 둘 다 정확도 주장이 아니라 충실성/안전성 속성이다.

### 외부 벤치마크 — 정확도는 우월이 아니라 비열등

균형 잡힌 70개 변이 전문가 골드 스탠다드에서 3분류 정확도는 결정론적 모드 0.557(95% CI 0.443–0.671), 무검색 LLM 0.586(0.471–0.700), 검색을 갖춘 생성 모드 0.600(0.486–0.714)이었다; 그림 4는 대응하는 혼동(confusion) 구조를 보고한다. 신뢰구간이 크게 겹치며 쌍별 차이가 유의하지 않다: 정확 McNemar 검정은 검색-대-무검색에서 p = 1.0(불일치 쌍 29개 중 검색 우위 15개, 무검색 우위 14개), 검색-대-규칙에서 p = 0.61(불일치 15개 중 9 대 6)을 준다. 따라서 우리는 명시적으로 검색이 더 정확하다고 주장하지 않는다; 적절한 주장은 비열등성이다. 검색 축은 가장 높은 점추정치와 가장 강한 oncogenic 클래스 재현율(0.79)을 보였으나, 모든 방법에서 가장 어려운 클래스는 VUS였고(재현율 0.37) LLM은 이를 oncogenicity 판정으로 과대 재분류하는 경향이 있었다. VUS로 오분류된 일곱 개의 oncogenic 변이는 커버리지가 얕은 희귀 변이였다 — 주로 PTEN과 EZH2(7개 중 5개: PTEN R130Q, T131I, H123R, P204A 및 EZH2 R684C), 추가로 BRAF G469A와 EZH2 V626M(후자는 검색 근거 0개) — 70개 전체 평균 2.2개 대비 평균 1.0개의 근거 항목만 지녔다. 따라서 이들의 누락은 추론 실패가 아니라 근거 희소성을 반영하며, 보류-가-옳다는 서사를 강화한다: 변이 특이적 근거가 거의 없는 상태에서 시스템은 추측하기보다 정직하게 VUS로 기본 설정했다. 5분류 정확도는 모든 방법에서 적당했으며(0.357–0.457), 이 규모에서 5분류 VICC 과제의 본질적 난이도와 일치한다.

![Horak 3분류 혼동 행렬](figures/F5_horak_confusion.png)

**그림 4. Horak 3분류 혼동 행렬(생성 모드 + 검색 대 골드, n = 70).** 정확도 0.600, oncogenic 재현율 0.79; VUS가 가장 어려운 클래스다. 결과는 우월이 아니라 비열등하다(McNemar p = 1.0 대 무검색, 0.61 대 규칙).

### 누출 통제 및 견고성

외견상의 검색 이득은 원칙적으로 누출 — 코퍼스가 최근의 정답 진술 근거를 포함하거나, 모델이 유명 변이를 회상함 — 을 반영할 수 있으므로, 우리는 여러 통제를 수행했다(그림 5 및 표 1).

**시간적 코퍼스 홀드아웃.** 검색 코퍼스를 연속적 컷오프 이전 문헌으로 제한해도 3분류 정확도가 저하되지 않았다: 전체 코퍼스(988개 근거 항목) 0.586; 2018년 이전(885개) 0.629; 2015년 이전(666개) 0.600; 2012년 이전(459개 항목, 절반 미만이며 2022년 골드 스탠다드보다 10년 앞섬) 0.643. 시간적 스윕은 시간 필터링된 코퍼스를 재임베딩·재인덱싱하는 별도 실행이므로 그 전체 코퍼스 지점(0.586)은 주 파이프라인의 검색 정확도(0.600)와 미미하게 다르다; 둘은 같은 실행이 아니며 모두 ±0.11 폭의 전체 코퍼스 신뢰구간 내에 충분히 위치한다. 이 모든 점추정치가 그 구간 내에 있으므로 작은 상향 표류는 유의하지 않으며 향상으로 주장되지 않는다; 올바른 해석은 성능이 최근의 정답 진술 근거 검색에 의존하지 않는다는 것 — 코퍼스 누출 채널이 결과를 추동하지 않는다는 것이다. 무검색 파라메트릭 하한(0.586)이 참조로 함께 표시된다.

![시간적 코퍼스 홀드아웃](figures/F3_temporal.png)

**그림 5. 시간적 코퍼스 홀드아웃(Horak 골드, n = 70).** 점점 더 오래된 검색 코퍼스에서의 3분류 정확도를 무검색 파라메트릭 하한과 함께 표시; 2012년 이전 문헌으로 제한해도 정확도가 저하되지 않는다. 차이는 잡음 범위 내로, 정확도 이득이 아니라 누출 통제된 견고성이다.

**자기 근거 제외(LOVO).** 검색 전에 각 변이 자체의 큐레이션 CIViC 근거를 제거하는 것 — 가장 강력한 코퍼스 누출 통제 — 은 3분류 정확도를 통계적으로 변화시키지 않았다(0.614 대 전체 0.600; McNemar p = 1.0). 성능은 변이 자체의 정답 근거 검색에 의존하지 않는다.

**두 번째 모델.** gpt-4o로 복제하면 점추정치가 상승했으나(3분류 정확도 0.70 [95% CI 0.60–0.80], κ 0.51, 대 gpt-4o-mini 0.60/0.33) 그 차이는 유의하지 않았다(McNemar p = 0.21, n = 70). 특히 gpt-4o는 주 구성과 동일한 oncogenic 재현율(0.79)에 도달했다; 더 높은 점 정확도는 전적으로 VUS/benign 축에서 나왔으므로(더 정확한 VUS 및 benign 판정), 공유된 0.79 재현율은 gpt-4o 우위의 원천이 아니다. 올바른 해석은 발견이 더 작은 모델의 산물이 아니며 더 강한 모델에서도 악화되지 않는다는 것이지, gpt-4o가 더 낫다는 것이 아니다.

**임베딩 제거 실험.** 보류된 자기 근거의 recall@5는 임베더 간에 유사했으며(PubMedBERT 0.243, MiniLM 0.229, OpenAI 0.229), 따라서 임베딩 모델은 민감한 요인이 아니다 — 기껏해야 소폭의 도메인 모델 우위만 존재한다.

이 통제들은 코퍼스 누출 채널을 정량화하고 그것이 결과를 추동하지 않음을 보인다. 이들은 LLM 자체의 파라메트릭 누출을 통제하지 않으며, 이는 여전히 통제되지 않은 채 무검색 하한으로만 정량화된다.

### 분석 신호로서의 이중 모드 불일치

56개 변이 코호트 전반에서 생성 모드와 결정론적 모드 간 oncogenicity 일치도는 0.786(95% CI 0.679–0.893), tier 일치도는 0.571(0.446–0.696)이었고, 불일치 사례는 31개였다. 불일치는 압도적으로 미세했다: 31개 불일치 중 26개가 인접(한 단계)했고 단 5개만이 큰(gross) 불일치였다(그림 6). 유형별로는 17개가 tier 경계 불일치, 6개가 oncogenic 확신도(Oncogenic 대 Likely Oncogenic), 3개가 "규칙을 넘는(beyond-rules)" 교정(규칙은 driver로 과대 판정하나 LLM은 근거를 읽어 비driver로 판정: PIK3CA R88Q, PTEN R130\*, ESR1 E247K), 2개가 benign 라벨, 2개가 검증기 하향 판정, 1개가 LLM 과대 판정이었다. 불일치는 TP53에 집중되었고(7개 TP53 변이 모두 불일치) 희귀 변이보다는 tier 경계의 속성이었다(hotspot 불일치 0.54 대 비hotspot 0.56).

![이중 모드 불일치](figures/F4_discordance.png)

**그림 6. 이중 모드 불일치.** (a) 유형별 불일치(31개 중 26개 인접, 5개 큰 불일치). (b) KRAS G12V 맥락 의존성: oncogenicity는 안정적이나 대장선암에서 Tier I, 췌장선암에서 Tier II.

대표적인 맥락 의존성 사례가 이 신호가 해석 가능한 이유를 보여준다. KRAS G12V는 암종 전반에서 안정적인 oncogenicity 판정을 받았으나 맥락 의존적 tier를 받았다 — 대장선암에서 Tier I 대 췌장선암에서 Tier II — 이는 종양 유형 간 임상 실행 가능성 근거 강도의 진정한 차이를 반영하며, 정확히 평면적 규칙이 놓치는 구별이다(그림 6). 네 개의 다중 암종 변이 전체에서 oncogenicity는 안정적이었고 오직 KRAS G12V의 tier만 변동했다. 보조 분석에서 AlphaMissense–LLM oncogenicity 일치도 0.944(17/18), 정확 매칭이 놓친 CIViC 근거를 회복하는 밀집 축 회수 향상(PIK3CA H1047R에 결정적), 순효과가 양인 검증기(10개 tier를 변경, 6개는 규칙 쪽으로 4개는 반대로, tier 일치도를 0.518에서 0.571로 상승)를 발견했으며, 검증기 상한 교란이 제거되자 투표 신뢰도는 보정된 신호로 거동했다.

### 표 1. 정확도 및 누출 통제 요약(Horak 골드 스탠다드, n = 70, 3분류).

| 구성 | 3분류 정확도 | κ (3분류) | Oncogenic 재현율 | LLM+RAG 대비 검정 |
|---|---|---|---|---|
| 결정론적(규칙) | 0.557 [0.443–0.671] | 0.274 | — | McNemar p = 0.61 |
| 생성, 무검색 (파라메트릭 하한) | 0.586 [0.471–0.700] | 0.254 | — | McNemar p = 1.0 |
| **생성 + 검색 (주, gpt-4o-mini)** | **0.600 [0.486–0.714]** | **0.332** | **0.79** | — |
| 생성 + 검색, 코퍼스 < 2012 (시간적 스윕) | 0.643 † | 0.413 | 0.85 | 구간 내 |
| 생성 + 검색, LOVO (자기 근거 제거) | 0.614 [0.500–0.729] | 0.366 | 0.82 | McNemar p = 1.0 |
| 생성 + 검색, gpt-4o | 0.700 [0.600–0.800] | 0.506 | 0.79 | McNemar p = 0.21 |

주 구성과의 모든 차이는 유의하지 않다; 구간은 비모수 부트스트랩 95% CI이다(LOVO 및 gpt-4o CI는 주 행과 동일한 부트스트랩으로 변이별 3분류 정확성으로부터 재계산되었다). 어떤 구성도 정확도 향상을 확립하지 않는다. † 시간적 스윕 행은 검색 *코퍼스*가(테스트 세트가 아니라) 변하는 기술적 단일 실행이다; 이들에 대해서는 부트스트랩 CI나 McNemar 검정이 계산되지 않으며, 전체 시간적 스윕은 위와 그림 5에 보고된다.

---

## 고찰

### 주요 발견 및 임상적 함의

본 연구는 견고한 주장 하나와 신중히 한정된 두 주장을 제시한다. 견고한 주장은 충실성이다: 검색을 사용하면 시스템은 인용을 조작하지 않았고 검사 가능한 모든 사례에서 근거화·방향 존중·보류했으나, 동일한 무검색 LLM은 변이의 46.4%에서 인용을 조작했다. 임상 의사결정 지원에서 이는 한계적 정확도 이득보다 중요하다. 분자종양위원회에서 신뢰의 단위는 개별 주장과 그 출처다: 임상의가 한 줄 한 줄 감사할 수 있는 분류는 불확실해도 사용 가능한 반면, 발명된 PMID로 뒷받침된 자신만만한 분류는 우연히 옳더라도 사용할 수 없다. 충실성 계약은 이 요구를 보장으로 전환한다 — 시스템은 검색된 식별자만 인용하고 근거가 없을 때 보류한다 — 사후 점검이 아니라 구조적으로 출력을 감사 가능하게 만든다. 한정된 두 주장도 같은 안전 논리를 따른다. 검색은 자신만만하게 과대 판정된 변이의 21.4%를 근거 정초 VUS로 재분류하여, 책임질 수 없는 driver 판정을 정직한 보류로 대체했다; 그리고 정확도는 우월이 아니라 비열등했는데, 우리는 이를 겹치는 구간으로부터 과대 해석하지 않고 그대로 진술한다. 임상적 해석은, 정초가 정확도 손실 없이 감사가능성과 자신만만한 과대 판정의 감소를 산다는 것이다 — 책임질 수 없는 오류가 인정된 불확실성보다 더 나쁜 환경에서 유리한 거래다.

### 선행 연구와의 비교

검색 충실성이라는 *개념* 자체는 우리 것이 아니다. ALCE [12]는 인용 정밀도·재현율의 자동 평가를 정형화했고, RAGAS와 MedCite [20]의 의학 인용 계열은 충실성·검증가능 인용 점수화를 자동화했으며, 보류를 동반한 결정론적 가드레일은 일반 임상 RAG에서 이미 확립되어 있다. 우리의 기여는 그 *적용과 보장*이며 세 가지로 요약된다. 첫째, 우리는 충실성 — 환각 인용률, 인용 근거화, *방향성* 충실성 지표, 보류 재현율 — 을 종양학 리포트를 실제로 좌우하는 두 표준 분류 과제(ClinGen/CGC/VICC oncogenicity와 AMP/ASCO/CAP tier)에 대해 정확도와 *나란히* 보고하는 1순위 평가축으로 삼는다 — 이 하위 분야의 기존 도구 [6,7,8,19]는 정확도·일치도만 보고하고 환각이나 보류는 결코 보고하지 않는다. 둘째, 우리는 충실성을 *구조적으로* 최악조건 보장한다 — 번들 외 인용 0%, 근거가 없거나 모순될 때 강제 보류 — 선행 프레임워크가 제공하는 측정·완화 수준의 속성이 아니다. 셋째, 시간적 홀드아웃과 자기 근거 제외 통제로 이 거동이 누출 산물이 아님을 보이며, 이는 어떤 선행 LLM-변이 연구도 보고하지 않았다. 우리는 인용 가능한 규칙 엔진 자체를 새로운 것으로 주장하지 않는다 — OncoVI [19]가 이미 각 VICC 기준을 그 근거 출처에 매핑한다 — 다만 이 이중 모드 설계 위에 얹은 충실성 보고와 구조적 보장만을 기여로 주장한다.

기존 규칙 기반 생태계 [6,7,8]에 비해 구별되는 기여는 tier 정확도 향상이 아니라 정직한 보류를 동반한 즉석의 근거 정초 자연어 정당화이며; 우리의 결정론적 모드는 경쟁자가 아니라 그 생태계의 단순화된 일원이다. 최근 LLM-변이 연구 [14,15]에 비해 구별되는 기여는 누출 없는 충실성 감사 — ALCE [12]의 정신에 따르되 구절이 아니라 데이터베이스 식별자에 대해 — 와 누출 통제다. 무검색 모델이 변이를 더 높은 확신으로 과대 판정한다는 우리의 관찰은 Lin et al. [14]이 보고한 과대 분류 경향을 독립적으로 재현하며, 검색 정초가 이를 억제함을 보인다.

두 편의 동시기 연구가 가장 가까운 이웃이며 명시적 차별화가 필요하다. CIViC-Fact [16]는 암 변이 주장을 전문(full-text)의 문장 수준 지지/반박 근거에 연결하는 CIViC 기반 벤치마크를 구축하고 사실 검증용 검증기를 미세조정한다; 우리의 과제는 다르다 — 인용 근거화 계약 하에서 누출 통제로 평가되는 생성적 2축 분류(VICC oncogenicity와 AMP/ASCO/CAP tier) — 그러나 변이에 대한 충실성이라는 틀은 인접하며, 우리 시스템을 그 위에서 평가하는 것은 자연스러운 확장이다. Precision Grounding [17] 역시 환각을 줄이기 위해 변이 LLM을 큐레이션된 데이터베이스에 정초시키지만, 표준화된 분류가 아니라 자유 텍스트 요약을 대상으로 한다. 규칙 기반 비교 대상 중 OncoVI [19]는 93개 가이드라인 골드 세트에서 80%에 도달하는 완전한 ClinGen/CGC/VICC 구현으로, 의도적으로 단순화한 우리의 규칙 모드보다 강한 결정론적 기준선이며 향후 벤치마크의 명백한 정면 비교 대상이다. 높은 의사결정 정확도에 도달하지만 가이드라인을 올바르게 인용하는 비율이 75.5%에 그치는 Ferber et al. [18] 같은 자율 임상 에이전트에 비해, 우리의 기여는 에이전트적 범위가 아니라 바로 그 충실성 보장이다. 우리의 귀속 지표는 MedCite [20]의 의학 인용 평가 계열을 따르며, 누출 통제는 벤치마크 오염 문헌 [21]에서 동기를 얻는다. 그림 7은 이 접근들을 두 축 — 근거 정초 충실성·감사가능성 대 범위·자율성 — 에 배치하여, 본 연구가 자율 에이전트나 순진한 LLM이 도달하지 못하는 높은 충실성 영역에 위치하면서도 고정된 규칙 엔진보다 더 큰 유연성을 유지함을 보인다.

![충실성·감사가능성과 범위·자율성에 따른 접근법의 개념적 위치](figures/F7_positioning.png)

**그림 7. 구조적으로 충실한 해석의 위치.** 접근법을 근거 정초 충실성·감사가능성(x)과 범위·자율성(y)으로 배치했다. 본 연구는 높은 충실성 영역 — 인용 조작 0%, 근거화 100% — 을 차지하며, 결정론적 규칙 엔진보다 유연하고 자율 임상 에이전트(예: Ferber et al. [18]는 가이드라인을 75.5%만 올바르게 인용)나 무검색 LLM보다 귀속이 강하다. 위치는 개념적이며, 보고된 값은 각 인용 연구가 자체 과제·데이터에서 얻은 것으로 동일 입력에 대한 정면 비교가 아니다.

### 충실한 분류에서 의사결정 지원 인터페이스로

충실성은 의사결정을 내리는 사람에게 도달할 때 가장 유용하다. 대시보드는 사용 시점에 계약을 운용한다(그림 8): 모든 해석이 1차 출처와 함께 클릭 가능한 링크로 표시되어 사용자가 각 주장을 한 단계로 검증할 수 있고, 근거 정초 채팅은 즉흥적으로 답하기보다 검색된 근거를 넘어서는 답을 거부한다. 두 실제 사례가 대비를 보여준다. **피부 흑색종의 BRAF V600E**에 대해 두 모드는 모두 Oncogenic / Tier I을 반환하고 각 주장은 그 CIViC 출처(EID1398, EID1409, BRIM-3 vemurafenib 근거)로 연결된다; 변이가 실행 가능한지 물으면 채팅은 식별자를 첨부하여 그 번들로부터 답한다. 변이 특이적 근거가 검색되지 않는 대장선암의 절단형 변이 **APC R1450\***에 대해서는 두 모드 모두 VUS를 보고하고 채팅은 driver로 과대 판정하기보다 "I cannot answer from the available evidence"라고 답한다 — 3.1–3.2절에서 정량화된 바로 그 근거 정초-대-보류 거동이 이제 사용 시점에 가시화된다. 분자종양위원회에서 이는 사용 가능한 보조 도구와 위험한 보조 도구를 가르는 거동이다: 감사 가능하고 출처가 연결된 답, 또는 근거가 불충분하다는 명시적 인정이, 책임질 수 없는 판단을 대체하는 것이 아니라 인간의 결정을 뒷받침한다. 이 인터페이스는 연구·교육용 데모이며 임상 배포용으로 검증되지 않았고, 어떤 임상 사용도 아래에 서술한 전향적 평가를 요구한다는 점을 강조한다.

![의사결정 지원 대시보드: 실제 코호트 데이터로 렌더링한 근거 정초 변이 보기와 채팅](figures/F6_dashboard.png)

**그림 8. 의사결정 지원 대시보드(실제 코호트 데이터로 렌더링한 대표적 변이 보기).** 피부 흑색종의 BRAF V600E에 대해 생성 모드와 결정론적 모드가 일치하고(Oncogenic, Tier I) 모든 진술이 그 CIViC 출처(예: EID1398, EID1409)로 연결된다; 근거 정초 채팅은 검색 번들로부터만 답한다. 변이 특이적 근거가 없는 절단형 변이 APC R1450\*에 대해서는 두 모드 모두 VUS를 보고하고 채팅은 driver로 과대 판정하기보다 보류한다("I cannot answer from the available evidence"). 근거 식별자와 외부 데이터베이스 링크(OncoKB, ClinVar, cBioPortal, COSMIC, DGIdb, ClinicalTrials.gov)는 실제 앱에서 클릭 가능하다.

### 정확도 주장을 위한 검정력 있는 평가를 향하여

우리는 정확도 우위를 주장하지 않았는데, n = 70에서 관찰된 어떤 차이(검색 대 무검색 +0.014; 대 규칙 +0.043)도 통계적으로 유의하지 않기 때문이다. 그러한 주장의 확립은 표현의 문제가 아니라 연구 설계의 문제이며, 직접 실행할 수 있도록 다음을 명시한다. (i) **사전 지정된 관심 효과와 검정력 분석.** 불일치 쌍 비율이 약 0.4인 쌍별 McNemar 비교에서 절대 3분류 정확도 이득 약 0.05를 80% 검정력으로 검출하려면 수백 개 수준의 변이가, 0.03 이득에는 대략 천 개가 필요하다; 목표 n은 데이터 가용성이 아니라 이 계산으로부터 고정해야 한다. (ii) **더 크고 클래스 균형이 잡힌 누출 통제 벤치마크.** 유전자와 다섯 VICC 클래스 전반에 걸쳐 층화된, 검색 코퍼스와 독립적이며 모델 학습 컷오프 이후의 출처에서 추출한 최소 수백 개의 전문가 분류 체세포 변이를 모아, 코퍼스 누출과 파라메트릭 누출을 별도 통제가 아니라 같은 설계 안에서 중화한다. (iii) **순서형 클래스별 종단점.** 클래스별 정밀도·재현율·F1과 전체 혼동 행렬을 보고하고, 평면적 정확도보다 순서형 5분류 과제에 더 적합한 macro-F1과 이차 가중 κ를 주 종단점으로 채택한다. (iv) **변동성 특성화.** 최소 5개의 시드·온도 설정과 투표 크기 n ∈ {1, 3, 5}를 실행하여 평균 ± SD를 보고한다; 현재의 단일 실행 추정치는 어느 방향으로도 유의성 주장을 뒷받침할 수 없다. (v) **사전 등록 분석.** 비열등성 마진을 사전 등록하고, 초과될 때에만 우월성 검정을 두 분류 축에 걸친 다중성 통제와 함께 수행한다. (vi) **전문가 판정.** 21.4% 과대 판정 억제와 규칙을 넘는 교정을, 맹검된 인증 분자병리 전문가 패널이 각 VUS 재분류를 적절한 교정인지 과도하게 보수적인 하향 판정인지 라벨링하게 함으로써, 행동 신호에서 정답 주장으로 전환한다. 이 요소들이 갖춰질 때에만 변호 가능한 정확도 주장 — 그리고 별도로 검증된 임상 효용 주장 — 이 정당화된다.

구체적으로, 세 가지 추가가 이 더 풍부하고 누출 통제된 평가를 제공한다. 첫째, **골드 세트를** 70개 Horak 부분집합에서 전체 93개 ClinGen/CGC/VICC 가이드라인 세트로 확장하여 동일 변이에서 OncoVI 규칙 엔진 [19]과의 정면 비교를 가능하게 한다. 둘째, ClinVar의 체세포 oncogenicity 제출(2024년 개시)에서 **깨끗한 시간적 홀드아웃을** 추가한다; 이는 대부분의 사전학습 코퍼스보다 늦으며 고유 VICC 라벨을 지녀 코퍼스 누출과 파라메트릭 누출 채널을 하나의 설계에서 중화한다. 셋째, 우리의 인용 정초가 독립적 귀속 과제로 전이되는지 시험하기 위해 CIViC-Fact 벤치마크 [16](CC0, 커밋 가능)에서 **충실성을 교차 평가한다.** 직교적 기능 검증 — oncogenicity 판정을 MaveDB 및 ProteinGym의 심층 돌연변이 스캐닝 적합도 점수와 상관 — 은 추가 전문가 라벨 없이 구성 타당도를 더한다. 평가는 또한 **여러 모델 계열에 걸쳐야** 한다 — 선행 LLM-변이 벤치마크 [14]처럼 독점 GPT 계열과 더불어 Llama 3.1, Mixtral 같은 공개 가중치 모델을 포함하여, 충실성 아키텍처와 그 정확도 거동이 단일 모델의 특이성이 아니라 벤더를 넘어 일반화됨을 입증한다; 모델 간 일치는 추가로 보정된 신뢰도 및 보류 신호로 기능할 수 있다. 이들은 향후 과제로 범위가 한정되며 여기서는 실행되지 않는다.

평가를 넘어, 이 요소들은 자율 임상 에이전트가 가장 약한 바로 그 지점에서 그들을 능가하는 구체적 방법을 시사한다. 그러한 에이전트는 단일 강력 모델로 도구 사용을 구동하며, Ferber et al. [18]이 보고하듯 공개 가중치 모델(Llama-3 70B, Mixtral)은 그 구동 역할에서 신뢰성이 낮고 인용 정확도는 사람 판정 75.5%에 그친다. 충실성 우선 대안은 이 설계를 뒤집는다. 공개 모델이 검색을 *구동*하게 하는 대신, 여러 모델 — gpt-4o-mini, gpt-4o와 공개 가중치 Llama 3.1, Mixtral — 을 *단일 고정 검색 근거 집합에 대한 독립적 평가자*로 실행하며(도구 호출 신뢰성은 무관), 판정과 인용된 근거 식별자 양쪽에 대한 모델 간 일치를 보정된 신뢰도로 삼아 불일치를 보류로 라우팅한다. 여기에 주장 수준 귀속 검사 — 각 주장이 인용된 구절에 의해 함의(entailment)되는지 검증 — 를 결합하면 단일 사람 판정 인용 점수를 자동·재현 가능한 인용 충실성 지표로 대체하며, 시간적 및 자기 근거 제외 홀드아웃 하의 위험–커버리지 곡선이 보류 단위당 확보되는 안전성을 정량화한다. 이 묶음은 에이전트 구동자로서 실패하는 바로 그 공개 모델을 충실성 신호로 재사용하여 오프라인에서 실행 가능하다. 우리는 이를 여기서 보고된 결과가 아니라 다음 방법론적 단계로 제시한다.

### 한계

여러 한계가 현재의 주장을 한정한다. 절대 정확도는 적당하다 — 5분류 정확도 0.36–0.46, 3분류 약 0.60 — 이는 이 규모에서 5분류 VICC 과제의 본질적 난이도를 반영한다; 기여는 정확도가 아니라 충실성이다. VUS 보정은 진정한 약점이다: LLM은 불확실 변이를 oncogenicity 판정으로 과대 재분류한다(VUS 재현율 0.37). 희귀 변이 커버리지는 얕다: oncogenic-대-VUS 누락은 근거 항목이 적은 변이이므로 정직한 보류 거동이 올바르게 발동하지만 재현율을 대가로 치르며, 이는 더 넓은 근거 출처와 파운데이션 모델 사전 확률의 더 강한 가중을 동기화한다. LLM 파라메트릭 누출은 우리의 어떤 실험으로도 통제되지 않는다; 시간적 및 LOVO 통제는 검색 코퍼스 채널만 다루며, 무검색 하한이 파라메트릭 채널의 유일한 정량화다. 본 연구는 단일 샘플, 유전자/단백질 변화 수준, 70개 변이 외부 세트와 단일 주모델(gpt-4o-mini) 기반이다; gpt-4o 복제는 단일 모델 의존성을 완화하지만 제거하지는 않는다. 결정론적 기준선은 단순화되어 있다 — 방향성을 인식하므로 허수아비는 아니지만 가이드라인 인증을 받지 않았다. 끝으로 코호트 선택은 암종당 AlphaMissense 전용 및 근거 없는 변이의 수를 제한하므로, 비용 통제를 위해 398개 고유 변이 중 56개가 분류되었다. 이러한 제약과 유의하지 않은 정확도 비교가, 우리가 본 연구를 "더 정확하다"가 아니라 "충실하고 비열등하다"로 틀짓는 이유다.

---

## 결론

본 연구는 구조적으로 충실한 체세포 변이 해석기와, 인용 근거 기반 검색이 감사가능성을 보장하고 자신만만한 파라메트릭 과대 판정을 억제하면서도 현재 규모에서 분류 정확도를 비열등하게 유지함을 보이는 누출 인식 평가를 제시한다. 임상 의사결정 지원에서 충실성과 감사가능성은 정확도에 부차적인 것이 아니라 신뢰받기 위한 전제 조건이다: 불확실할 수는 있어도 결코 책임질 수 없지 않은 시스템이, 아무도 확인할 수 없는 이유로 가끔 옳은 시스템보다 분자종양위원회에서 더 안전하다. 정확도 주장으로 가는 길은 우리가 설계를 명시한, 더 크고 검정력 있으며 누출 통제된 전문가 판정 벤치마크이며, 이는 전향적 임상 검증을 향한 자연스러운 다음 단계다. 재현을 위해 모든 코드와 데이터 스냅샷을 공개한다.

---

## 데이터 및 코드 가용성

모든 소스 코드, 재현 스크립트, 커밋된 데이터 스냅샷, 그림 생성 코드는 프로젝트 저장소(`https://github.com/<USERNAME>/<REPO>`, 출판 시 공개)에서 이용 가능하며, 모든 결과·그림·표는 저장소의 스크립트로 커밋된 데이터로부터 재현 가능하다. 시스템은 커밋된 스냅샷에서 오프라인으로 실행되며, 네트워크 접근은 데이터 수집 스크립트에 국한된다. 크거나 라이선스가 제한된 산출물 — 영속적 Chroma 밀집 인덱스, 전체 AlphaMissense TSV(CC BY-NC-SA), Horak 보충 표 — 은 커밋되지 않으며 저장소 스크립트로 재현된다; Horak 전문가 라벨은 재분배되지 않는다. 비밀값은 환경 변수 이름(`OPENAI_API_KEY`)으로만 참조되며; 어떤 키, 독점 로직, 환자 데이터도 포함되지 않는다. 라이선스는 전반에 걸쳐 준수된다: CIViC는 CC0, ClinicalTrials.gov와 ClinVar는 공개, TCGA 개방 접근 계층은 인용되며, AlphaMissense는 CC BY-NC-SA(커밋되지 않음), Horak 라벨은 재분배되지 않는다.

*면책: 본 시스템은 연구·교육 목적 한정이며 임상 의사결정용으로 검증되지 않았다; 모든 입력은 공개 TCGA 코호트 및 지식베이스에서 유래한다.*

---

## References

1. Horak P, Griffith M, Danos AM, et al. Standards for the classification of pathogenicity of somatic variants in cancer (oncogenicity): Joint recommendations of Clinical Genome Resource (ClinGen), Cancer Genomics Consortium (CGC), and Variant Interpretation for Cancer Consortium (VICC). *Genet Med* 2022;24(5):986–998. doi:10.1016/j.gim.2022.01.001
2. Li MM, Datto M, Duncavage EJ, et al. Standards and Guidelines for the Interpretation and Reporting of Sequence Variants in Cancer: A Joint Consensus Recommendation of the Association for Molecular Pathology, American Society of Clinical Oncology, and College of American Pathologists. *J Mol Diagn* 2017;19(1):4–23. doi:10.1016/j.jmoldx.2016.10.002
3. Chakravarty D, Gao J, Phillips S, et al. OncoKB: A Precision Oncology Knowledge Base. *JCO Precis Oncol* 2017;1:1–16. doi:10.1200/PO.17.00011
4. Tate JG, Bamford S, Jubb HC, et al. COSMIC: the Catalogue Of Somatic Mutations In Cancer. *Nucleic Acids Res* 2019;47(D1):D941–D947. doi:10.1093/nar/gky1015
5. Griffith M, Spies NC, Krysiak K, et al. CIViC is a community knowledgebase for expert crowdsourcing the clinical interpretation of variants in cancer. *Nat Genet* 2017;49(2):170–174. doi:10.1038/ng.3774
6. Li Q, Ren Z, Cao K, Li MM, Wang K, Zhou Y. CancerVar: An artificial intelligence–empowered platform for clinical interpretation of somatic mutations in cancer. *Sci Adv* 2022;8(18):eabj1624. doi:10.1126/sciadv.abj1624
7. Tamborero D, Rubio-Perez C, Deu-Pons J, et al. Cancer Genome Interpreter annotates the biological and clinical relevance of tumor alterations. *Genome Med* 2018;10(1):25. doi:10.1186/s13073-018-0531-8
8. Nakken S, Fournous G, Vodák D, et al. Personal Cancer Genome Reporter: variant interpretation report for precision oncology. *Bioinformatics* 2018;34(10):1778–1780. doi:10.1093/bioinformatics/btx817
9. Cheng J, Novati G, Pan J, et al. Accurate proteome-wide missense variant effect prediction with AlphaMissense. *Science* 2023;381(6664):eadg7492. doi:10.1126/science.adg7492
10. Brandes N, Goldman G, Wang CH, et al. Genome-wide prediction of disease variant effects with a deep protein language model. *Nat Genet* 2023;55(9):1512–1522. doi:10.1038/s41588-023-01465-0
11. Frazer J, Notin P, Dias M, et al. Disease variant prediction with deep generative models of evolutionary data. *Nature* 2021;599(7883):91–95. doi:10.1038/s41586-021-04043-8
12. Gao T, Yen H, Yu J, et al. Enabling Large Language Models to Generate Text with Citations. *Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing (EMNLP)* 2023:6465–6488. doi:10.18653/v1/2023.emnlp-main.398
13. Xiong G, Jin Q, Lu Z, et al. Benchmarking Retrieval-Augmented Generation for Medicine. *Findings of the Association for Computational Linguistics: ACL 2024* 2024:6233–6251. doi:10.18653/v1/2024.findings-acl.372
14. Lin K-H, Kao T-H, Wang L-C, et al. Benchmarking large language models GPT-4o, Llama 3.1, and Qwen 2.5 for cancer genetic variant classification. *npj Precis Oncol* 2025;9(1):141. doi:10.1038/s41698-025-00935-4

15. Lu S, Cosgun E. Boosting GPT models for genomics analysis: generating trusted genetic variant annotations and interpretations through RAG and Fine-tuning. *Bioinform Adv* 2025;5(1):vbaf019. doi:10.1093/bioadv/vbaf019
16. Reisle C, Grisdale CJ, Krysiak K, et al. Evaluating Language Models for Biomedical Fact-Checking: A Benchmark Dataset for Cancer Variant Interpretation Verification (CIViC-Fact). *bioRxiv* 2025;2025.09.10.675443. doi:10.1101/2025.09.10.675443
17. Du X, Nagy A, Oates MF, et al. Precision Grounding: Augmenting Large Language Models with Evidence-Based Databases for Trustworthy Genetic Variant Summarization. *medRxiv* 2025;2025.06.09.25329279. doi:10.1101/2025.06.09.25329279
18. Ferber D, et al. Development and validation of an autonomous artificial intelligence agent for clinical decision-making in oncology. *Nat Cancer* 2025. doi:10.1038/s43018-025-00991-6
19. Carta MG, Tögel L, Hölsken A, et al. Oncogenicity Variant Interpreter (OncoVI): oncogenicity guidelines implementation to support somatic variants interpretation in precision oncology. *medRxiv* 2024;2024.10.10.24315072. doi:10.1101/2024.10.10.24315072
20. Wang X, Tan M, Jin Q, et al. MedCite: Can Language Models Generate Verifiable Text for Medicine? *Findings of the Association for Computational Linguistics: ACL 2025* 2025:18891–18913.
21. Xu C, Guan S, Greene D, et al. Benchmark Data Contamination of Large Language Models: A Survey. *arXiv* 2024;arXiv:2406.04244.

> *참고문헌에 관한 주석:* 모든 항목은 문헌 조사 중 CrossRef/출판사 기록(제목, 저자, 연도, 발행처, DOI)에 대조하여 검증되었으며; DOI는 인용된 논문으로 연결된다. 원래 초안의 "Lin et al. 2025, *Retrieval-augmented generation for clinical variant interpretation*"은 기재된 대로 검증할 수 **없었다**(그러한 논문을 찾지 못함). 이는 검증된 두 편의 밀접하게 관련된 연구로 대체되었다: Lin et al. 2025(참고문헌 14, *npj Precision Oncology*의 암 변이 분류를 위한 LLM 벤치마크 — 제1저자/연도는 초안과 일치하나 제목과 범위는 다름)와 Lu & Cosgun 2025(참고문헌 15, RAG 기반 변이 주석 논문). 초안이 다른 "Lin" 논문을 의도했다면, 제출 전에 참고문헌 14를 재확인해야 한다.

### BibTeX

```bibtex
@article{Horak2022, title={Standards for the classification of pathogenicity of somatic variants in cancer (oncogenicity): Joint recommendations of Clinical Genome Resource (ClinGen), Cancer Genomics Consortium (CGC), and Variant Interpretation for Cancer Consortium (VICC)}, author={Horak, Peter and Griffith, Malachi and Danos, Arpad M. and Pitel, Beth A. and Madhavan, Subha and Liu, Xuelu and Chow, Cynthia and Williams, Heather and Carmody, Leigh and Barrow-Laing, Lisa and Rieke, Damian and Kreutzfeldt, Simon and Stenzinger, Albrecht and Tamborero, David and Benary, Manuela and Rajagopal, Padma Sheila and Ida, Cristiane M. and Lesmana, Harry and Satgunaseelan, Laveniya and Merker, Jason D. and Tolstorukov, Michael Y. and Campregher, Paulo Vidal and Warner, Jeremy L. and Rao, Shruti and Natesan, Maya and Shen, Haolin and Venstrom, Jeffrey and Roy, Somak and Tao, Kayoko and Kanagal-Shamanna, Rashmi and Xu, Xinjie and Ritter, Deborah I. and Pagel, Kym and Krysiak, Kilannin and Dubuc, Adrian and Akkari, Yassmine M. and Li, Xuan Shirley and Lee, Jennifer and King, Ian and Raca, Gordana and Wagner, Alex H. and Li, Marylin M. and Plon, Sharon E. and Kulkarni, Shashikant and Griffith, Obi L. and Chakravarty, Debyani and Sonkin, Dmitriy}, journal={Genetics in Medicine}, volume={24}, number={5}, pages={986--998}, year={2022}, doi={10.1016/j.gim.2022.01.001} }

@article{Li2017, title={Standards and Guidelines for the Interpretation and Reporting of Sequence Variants in Cancer: A Joint Consensus Recommendation of the Association for Molecular Pathology, American Society of Clinical Oncology, and College of American Pathologists}, author={Li, Marilyn M. and Datto, Michael and Duncavage, Eric J. and Kulkarni, Shashikant and Lindeman, Neal I. and Roy, Somak and Tsimberidou, Apostolia M. and Vnencak-Jones, Cindy L. and Wolff, Daynna J. and Younes, Anas and Nikiforova, Marina N.}, journal={The Journal of Molecular Diagnostics}, volume={19}, number={1}, pages={4--23}, year={2017}, doi={10.1016/j.jmoldx.2016.10.002} }

@article{Chakravarty2017, title={OncoKB: A Precision Oncology Knowledge Base}, author={Chakravarty, Debyani and Gao, Jianjiong and Phillips, Sarah and Kundra, Ritika and Zhang, Hongxin and Wang, Jiaojiao and others}, journal={JCO Precision Oncology}, volume={1}, pages={1--16}, year={2017}, doi={10.1200/PO.17.00011} }

@article{Tate2019, title={COSMIC: the Catalogue Of Somatic Mutations In Cancer}, author={Tate, John G. and Bamford, Sally and Jubb, Harry C. and Sondka, Zbyslaw and Beare, David M. and Bindal, Nidhi and others}, journal={Nucleic Acids Research}, volume={47}, number={D1}, pages={D941--D947}, year={2019}, doi={10.1093/nar/gky1015} }

@article{Griffith2017, title={CIViC is a community knowledgebase for expert crowdsourcing the clinical interpretation of variants in cancer}, author={Griffith, Malachi and Spies, Nicholas C. and Krysiak, Kilannin and McMichael, Joshua F. and Coffman, Adam C. and Danos, Arpad M. and others}, journal={Nature Genetics}, volume={49}, number={2}, pages={170--174}, year={2017}, doi={10.1038/ng.3774} }

@article{Li2022CancerVar, title={CancerVar: An artificial intelligence--empowered platform for clinical interpretation of somatic mutations in cancer}, author={Li, Quan and Ren, Zilin and Cao, Kajia and Li, Marilyn M. and Wang, Kai and Zhou, Yunyun}, journal={Science Advances}, volume={8}, number={18}, pages={eabj1624}, year={2022}, doi={10.1126/sciadv.abj1624} }

@article{Tamborero2018, title={Cancer Genome Interpreter annotates the biological and clinical relevance of tumor alterations}, author={Tamborero, David and Rubio-Perez, Carlota and Deu-Pons, Jordi and Schroeder, Michael P. and Vivancos, Ana and Rovira, Ana and Tusquets, Ignasi and Albanell, Joan and Rodon, Jordi and Tabernero, Josep and de Torres, Carmen and Dienstmann, Rodrigo and Gonzalez-Perez, Abel and Lopez-Bigas, Nuria}, journal={Genome Medicine}, volume={10}, number={1}, pages={25}, year={2018}, doi={10.1186/s13073-018-0531-8} }

@article{Nakken2018, title={Personal Cancer Genome Reporter: variant interpretation report for precision oncology}, author={Nakken, Sigve and Fournous, Ghislain and Vod{\'a}k, Daniel and Aasheim, Lars Birger and Myklebost, Ola and Hovig, Eivind}, journal={Bioinformatics}, volume={34}, number={10}, pages={1778--1780}, year={2018}, doi={10.1093/bioinformatics/btx817} }

@article{Cheng2023, title={Accurate proteome-wide missense variant effect prediction with AlphaMissense}, author={Cheng, Jun and Novati, Guido and Pan, Joshua and Bycroft, Clare and {\v{Z}}emgulyt{\.e}, Akvil{\.e} and Applebaum, Taylor and Pritzel, Alexander and Wong, Lai Hong and Zielinski, Michal and Sargeant, Tobias and Schneider, Rosalia G. and Senior, Andrew W. and Jumper, John and Hassabis, Demis and Kohli, Pushmeet and Avsec, {\v{Z}}iga}, journal={Science}, volume={381}, number={6664}, pages={eadg7492}, year={2023}, doi={10.1126/science.adg7492} }

@article{Brandes2023, title={Genome-wide prediction of disease variant effects with a deep protein language model}, author={Brandes, Nadav and Goldman, Grant and Wang, Charlotte H. and Ye, Chun Jimmie and Ntranos, Vasilis}, journal={Nature Genetics}, volume={55}, number={9}, pages={1512--1522}, year={2023}, doi={10.1038/s41588-023-01465-0} }

@article{Frazer2021, title={Disease variant prediction with deep generative models of evolutionary data}, author={Frazer, Jonathan and Notin, Pascal and Dias, Mafalda and Gomez, Aidan and Min, Joseph K. and Brock, Kelly and Gal, Yarin and Marks, Debora S.}, journal={Nature}, volume={599}, number={7883}, pages={91--95}, year={2021}, doi={10.1038/s41586-021-04043-8} }

@inproceedings{Gao2023, title={Enabling Large Language Models to Generate Text with Citations}, author={Gao, Tianyu and Yen, Howard and Yu, Jiatong and Chen, Danqi}, booktitle={Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing}, pages={6465--6488}, year={2023}, doi={10.18653/v1/2023.emnlp-main.398} }

@inproceedings{Xiong2024, title={Benchmarking Retrieval-Augmented Generation for Medicine}, author={Xiong, Guangzhi and Jin, Qiao and Lu, Zhiyong and Zhang, Aidong}, booktitle={Findings of the Association for Computational Linguistics: ACL 2024}, pages={6233--6251}, year={2024}, doi={10.18653/v1/2024.findings-acl.372} }

@article{Lin2025, title={Benchmarking large language models GPT-4o, Llama 3.1, and Qwen 2.5 for cancer genetic variant classification}, author={Lin, Kuan-Hsun and Kao, Tzu-Hang and Wang, Lei-Chi and Kuo, Chen-Tsung and Chen, Paul Chih-Hsueh and Chu, Yuan-Chia and Yeh, Yi-Chen}, journal={npj Precision Oncology}, volume={9}, number={1}, pages={141}, year={2025}, doi={10.1038/s41698-025-00935-4} }

@article{Lu2025, title={Boosting GPT models for genomics analysis: generating trusted genetic variant annotations and interpretations through RAG and Fine-tuning}, author={Lu, Shuangjia and Cosgun, Erdal}, journal={Bioinformatics Advances}, volume={5}, number={1}, pages={vbaf019}, year={2025}, doi={10.1093/bioadv/vbaf019} }
```
