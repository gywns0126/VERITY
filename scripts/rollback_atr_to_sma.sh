#!/bin/bash
# scripts/rollback_atr_to_sma.sh
# Phase 0 P-04 — ATR 산출법 SMA로 즉시 롤백
#
# === 실행 환경 (P-04) ===
# - 본인 로컬 machine 만 실행 가능
# - 사전 조건: gh CLI 인증 + repo write 권한
# - GitHub Actions runner 에서는 실행 X (workflow 가 secret 변경 권한 부재)
#
# === Production 영속화 경로 ===
# Production = GitHub Actions cron 사용 환경
# → GitHub Repository Secrets (gh secret set 으로 변경)
# → .env.production 파일은 사용 안 함 (백엔드 정적 호스팅)
#
# === 로컬 개발 영속화 경로 ===
# 로컬 테스트 시 → .env.development 파일

set -e

REPO="gywns0126/VERITY"

echo "=== ATR 산출법 SMA 로 롤백 ==="

# 1. gh CLI 인증 확인
gh auth status > /dev/null 2>&1 || {
    echo "❌ gh CLI 미인증. 'gh auth login' 후 재실행."
    exit 1
}

# 2. 사용자 확인
echo "다음 GitHub Secrets 를 변경합니다:"
echo "  ATR_METHOD: wilder_ema_14 → sma_14"
echo "  ATR_STOP_MULTIPLIER: 2.5 → 0 (ATR 손절 비활성, fallback -5% 작동)"
echo ""
read -p "진행할까요? [yes/NO]: " CONFIRM
[ "$CONFIRM" != "yes" ] && { echo "취소됨."; exit 0; }

# 3. GitHub Secrets 갱신 (Production 영속화)
echo "[1/4] GitHub Secrets 갱신..."
gh secret set ATR_METHOD --body "sma_14" --repo "$REPO"
gh secret set ATR_STOP_MULTIPLIER --body "0" --repo "$REPO"

# 4. 로컬 .env.development 갱신 (로컬 테스트용, optional)
if [ -f .env.development ]; then
    echo "[2/4] .env.development 갱신..."
    sed -i.bak 's/^ATR_METHOD=.*/ATR_METHOD=sma_14/' .env.development
    sed -i.bak 's/^ATR_STOP_MULTIPLIER=.*/ATR_STOP_MULTIPLIER=0/' .env.development
fi

# 5. git tag (audit trail)
TAG="atr-rollback-$(date +%Y%m%d-%H%M)"
echo "[3/4] git tag: $TAG"
git tag "$TAG"
git push origin "$TAG"

# 6. 텔레그램 알림 (Backlog B1: send_message 사용 — send_alert 함수 부재 회피)
echo "[4/4] 텔레그램 알림..."
python -c "
from api.notifications.telegram import send_message
send_message(
    f'⚠️ ATR 롤백 완료 (PM 수동 실행)\n'
    f'  ATR_METHOD: sma_14\n'
    f'  ATR_STOP_MULTIPLIER: 0 (fallback -5%)\n'
    f'  기존 holdings: atr_method_at_entry 그대로 유지\n'
    f'  git tag: ${TAG}'
)
" 2>/dev/null || echo "  (텔레그램 발송 실패, 로컬 환경 가능)"

echo ""
echo "✅ 롤백 완료. 다음 cron 부터 SMA 적용."
echo "   기존 holdings 는 entry method 보호 (변경 없음)."
echo ""
echo "다음 단계:"
echo "  - BrainMonitor 에서 stop_price 분포 확인"
echo "  - 24시간 후 신규 진입 종목의 atr_method_at_entry='sma_14' 확인"
