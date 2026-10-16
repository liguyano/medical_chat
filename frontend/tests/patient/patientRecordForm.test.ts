import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import PatientRecordForm from '@/components/patient/PatientRecordForm';

describe('护士患者录入表单', () => {
  it.each(['create', 'edit'] as const)('%s 模式不提供住院日期或状态选择', (mode) => {
    const html = renderToStaticMarkup(createElement(PatientRecordForm, {
      mode, onCancel: vi.fn(), onSubmit: async () => undefined,
    }));
    expect(html).not.toContain('datetime-local');
    expect(html).not.toContain('入院时间');
    expect(html).not.toContain('出院时间');
    expect(html).not.toContain('value="discharged"');
    expect(html).not.toContain('本次住院信息');
    expect(html).not.toContain('科室');
    expect(html).not.toContain('病区');
    expect(html).not.toContain('住院状态');
    expect(html).not.toContain('医保类别');
    expect(html).not.toContain('住院号');
    expect(html).not.toContain('床号');
    expect(html).not.toContain('护理级别');
    expect(html).not.toContain('入院来源');
  });
});
