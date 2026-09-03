import React, { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterAll, describe, expect, it, vi } from 'vitest';
import PatientLayout from '@/components/layout/PatientLayout';

vi.mock('next/navigation', () => ({ useRouter: () => ({ back() {} }), usePathname: () => '/patient/dialogue/1' }));
// Vitest uses the classic JSX transform for this repository's existing components.
vi.stubGlobal('React', React);
afterAll(() => vi.unstubAllGlobals());

describe('患者桌面布局隔离', () => {
  it('普通患者页面不挂载桌面对话布局', () => {
    const html = renderToStaticMarkup(createElement(PatientLayout, null, '普通页面'));
    expect(html).toContain('patient-mobile-frame');
    expect(html).not.toContain('patient-dialogue-shell');
    expect(html).not.toContain('<aside');
  });
  it('只有传入进度面板时才使用独立桌面侧栏容器', () => {
    const props = { desktopAside: '评估进度' } as React.ComponentProps<typeof PatientLayout>;
    const html = renderToStaticMarkup(createElement(PatientLayout, props, '聊天'));
    expect(html).toContain('patient-dialogue-shell');
    expect(html).toContain('<aside class="patient-dialogue-aside">评估进度</aside>');
    expect(html).toContain('聊天');
  });
});
