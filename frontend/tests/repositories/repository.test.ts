import { describe, expect, it } from 'vitest';
import { ApiCareRepository } from '@/lib/repositories/apiRepository';
import { getCareRepository } from '@/lib/repositories';
import { MockCareRepository } from '@/lib/repositories/mockRepository';

describe('repository selection', () => {
  it('按运行模式选择Mock或API实现', () => {
    expect(getCareRepository('mock')).toBeInstanceOf(MockCareRepository);
    expect(getCareRepository('api')).toBeInstanceOf(ApiCareRepository);
  });
});
