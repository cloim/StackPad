import React from 'react';
import { UsageBar } from '../components/UsageBar.jsx';
import { t } from '../i18n.js';

function AiUsageWidget({ api, settings }) {
  return <UsageBar api={api} expected={settings?.usage_providers?.length || 0} />;
}

export default { name: () => t('AI 사용량'), order: 10, View: AiUsageWidget };
