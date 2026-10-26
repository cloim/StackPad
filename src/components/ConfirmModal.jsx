import React from 'react';
import { Modal } from './Modal/Modal.jsx';
import { t } from '../i18n.js';

// Confirms one destructive or irreversible choice; Cancel keeps everything as it was.
export function ConfirmModal({ isOpen, title, message, confirmLabel, danger = true, onConfirm, onCancel }) {
  return <Modal isOpen={isOpen} onClose={onCancel} title={title} size="sm" draggable={false} footer={<>
    <button type="button" className="secondary" onClick={onCancel}>{t('취소')}</button>
    <button type="button" className={danger ? 'danger' : 'primary'} onClick={onConfirm}>{confirmLabel}</button>
  </>}><p className="whitespace-pre-wrap text-[13px] leading-[1.9]">{message}</p></Modal>;
}
