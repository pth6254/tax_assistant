"""Supported consultation flows; questions and document prompts are not legal eligibility rules."""

CASE_KINDS = {
    'income_tax': {
        'label': '종합소득세', 'date_label': '귀속연도',
        'questions': (
            ('wage_income', '근로소득 총급여액(비과세 제외, 근무지가 둘 이상이면 합계)은 얼마인가요? 없다면 0원을 입력해 주세요.', 'amount', None),
            ('income', '사업소득 총수입금액은 얼마인가요? 없다면 0원을 입력해 주세요.', 'amount', None),
            ('expense', '사업소득 필요경비는 얼마인가요?', 'amount', None),
            ('sincere_business', '사업용계좌 신고 등 성실사업자 요건에 해당하나요?', 'boolean', None),
            ('other_income', '연금·기타소득 등 그 밖의 종합소득금액(필요경비·공제 차감 후)은 얼마인가요? 없다면 0원을 입력해 주세요.', 'amount', None),
            ('interest_income', '국내 예금·채권 이자소득 연간 합계는 얼마인가요? 없다면 0원을 입력해 주세요.', 'amount', None),
            ('dividend_gross_up', '내국법인 배당소득 연간 합계는 얼마인가요? 없다면 0원을 입력해 주세요.', 'amount', None),
            ('withheld', '이자·배당이 국내에서 원천징수되었나요?', 'boolean', None),
            ('personal_deduction_count', '기본공제 대상 인원은 본인을 포함해 몇 명인가요?', 'count', None),
            ('other_deductions', '기본공제 외 소득공제(추가공제·연금보험료 등) 합계는 얼마인가요? 없다면 0원을 입력해 주세요.', 'amount', None),
            ('itemized_special_credits', '보험료·의료비·교육비 등 특별소득공제나 특별세액공제를 신청하나요? (신청하면 표준세액공제를 받지 않습니다)', 'boolean', None),
            ('other_tax_credits', '근로소득·배당·표준세액공제 외 세액공제(자녀·연금계좌·의료비 등) 합계는 얼마인가요? 없다면 0원을 입력해 주세요.', 'amount', None),
            ('prepaid_tax', '이미 낸 세금(근로소득 원천징수·중간예납 등, 이자·배당 원천징수 제외)은 얼마인가요? 없다면 0원을 입력해 주세요.', 'amount', None),
        ),
        'documents': (
            ('wage_proof', '근로소득 원천징수영수증', '총급여액과 원천징수세액 확인 자료', 'wage_income'),
            ('income_proof', '수입금액 확인 자료', '사업 수입금액을 확인할 수 있는 자료', 'income'),
            ('expense_proof', '필요경비 확인 자료', '필요경비를 확인할 자료', 'expense'),
            ('financial_proof', '금융소득 자료', '이자·배당 지급명세·원천징수 내역', 'interest_income'),
            ('deduction_proof', '공제 확인 자료', '공제 항목을 확인할 자료', 'other_deductions'),
            ('credit_proof', '세액공제 자료', '세액공제 항목을 확인할 자료', 'other_tax_credits'),
        ),
    },
    'capital_gains': {
        'label': '양도소득세', 'date_label': '양도일·자료 조회 기준일',
        'questions': (
            ('transfer_price', '양도가액은 얼마인가요?', 'amount', None),
            ('acquisition_price', '취득가액은 얼마인가요?', 'amount', None),
            ('expenses', '취득·양도 관련 필요경비는 얼마인가요?', 'amount', None),
            ('holding_years', '보유기간은 몇 년인가요? (완료된 연수)', 'count', None),
            ('asset_type', '양도 자산은 무엇인가요? (비사업용 토지·분양권·주식은 계산하지 않습니다)', 'choice', ('주택', '토지·건물')),
            ('is_one_home', '양도일 현재 1세대 1주택인가요?', 'boolean', None),
            ('residence_years', '보유기간 중 거주한 기간은 몇 년인가요? (완료된 연수)', 'count', None),
            ('acquired_in_adjusted_area', '취득 당시 조정대상지역이었나요?', 'boolean', None),
            ('multi_home_surcharge', '조정대상지역 다주택 중과 대상인가요?', 'choice', ('없음', '2주택', '3주택이상')),
        ),
        'documents': (
            ('transfer_contract', '양도 계약 자료', '양도가액·양도일 확인 자료', None),
            ('acquisition_contract', '취득 계약 자료', '취득가액·취득일 확인 자료', None),
            ('expense_proof', '필요경비 증빙', '경비 확인 자료', 'expenses'),
            ('residence_proof', '주택 관련 자료', '보유·거주·주택 수 확인 자료', 'is_one_home'),
        ),
    },
    'inheritance': {
        'label': '상속세', 'date_label': '상속개시일·자료 조회 기준일',
        'questions': (
            ('estate_value', '상속재산가액은 얼마인가요?', 'amount', None),
            ('debts', '채무·공과금 합계는 얼마인가요?', 'amount', None),
            ('spouse_inheritance', '배우자가 상속받는 금액은 얼마인가요?', 'amount', None),
            ('children_count', '자녀는 몇 명인가요?', 'count', None),
        ),
        'documents': (
            ('estate_proof', '상속재산 자료', '재산목록·평가 자료', None),
            ('debt_proof', '채무·공과금 자료', '채무 증빙', 'debts'),
            ('family_proof', '가족관계 자료', '상속인 관계 확인 자료', None),
            ('spouse_proof', '배우자 상속 자료', '배우자 상속분 확인 자료', 'spouse_inheritance'),
        ),
    },
    'gift': {
        'label': '증여세', 'date_label': '증여일·자료 조회 기준일',
        'questions': (
            ('gift_amount', '증여재산가액은 얼마인가요?', 'amount', None),
            ('relation', '증여자와의 관계는 무엇인가요?', 'choice', ('배우자', '직계존비속', '기타친족', '기타')),
            ('is_minor', '수증자가 미성년자인가요?', 'boolean', None),
            ('prior_gifts_10y', '같은 증여자에게서 10년 내 받은 증여액은 얼마인가요?', 'amount', None),
        ),
        'documents': (
            ('gift_proof', '증여재산 자료', '증여 계약·재산 평가 자료', None),
            ('family_proof', '관계 확인 자료', '증여자와 수증자의 관계 자료', None),
            ('prior_gift_proof', '과거 증여 자료', '10년 내 증여 내역', 'prior_gifts_10y'),
        ),
    },
    'vat': {
        'label': '부가가치세', 'date_label': '과세기간 종료일·자료 조회 기준일',
        'questions': (
            ('sales', '과세기간의 총매출액은 얼마인가요?', 'amount', None),
            ('purchases', '매입액은 얼마인가요?', 'amount', None),
            ('exempt_sales', '면세·영세율 매출로 분리할 금액은 얼마인가요?', 'amount', None),
            ('is_simplified', '간이과세자에 해당하나요?', 'boolean', None),
            ('business_type', '업종은 무엇인가요?', 'choice', ('소매업', '음식점업', '제조업', '숙박업', '건설업', '서비스업', '부동산임대업')),
        ),
        'documents': (
            ('sales_proof', '매출 자료', '매출 세금계산서·장부', None),
            ('purchase_proof', '매입 자료', '매입 세금계산서·장부', 'purchases'),
            ('exempt_proof', '면세·영세율 자료', '구분 매출 증빙', 'exempt_sales'),
            ('business_proof', '사업자 유형 자료', '과세유형·업종 확인 자료', None),
        ),
    },
    'penalty_tax': {
        'label': '가산세', 'date_label': '위반·납부 기준일·자료 조회 기준일',
        'questions': (
            ('unpaid_tax', '무신고·과소신고 또는 미납 본세는 얼마인가요?', 'amount', None),
            ('penalty_type', '어떤 가산세를 검토하나요?', 'choice', ('무신고', '과소신고', '납부지연')),
            ('is_negligent', '부정행위가 있는 경우인가요? (무신고·과소신고에만 적용)', 'boolean', None),
            ('days_late', '납부지연 일수는 며칠인가요?', 'count', None),
        ),
        'documents': (
            ('tax_notice', '본세·신고 자료', '신고서·고지서', None),
            ('due_date_proof', '기한·납부 자료', '기한과 실제 납부일 확인 자료', None),
            ('penalty_basis', '부정행위 판단 자료', '부정행위 관련 자료', 'is_negligent'),
        ),
    },
}


def case_kind(kind):
    return CASE_KINDS[kind]
