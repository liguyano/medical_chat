import { afterEach, describe, expect, it, vi } from 'vitest';
import { mapStaffUser } from '@/lib/api/mappers';
import { ApiCareRepository } from '@/lib/repositories/apiRepository';
import { MockCareRepository } from '@/lib/repositories/mockRepository';

function okResponse(data: unknown) {
  return new Response(
    JSON.stringify({ code: 'OK', message: '成功', data }),
    {
      status: 200,
      headers: { 'Content-Type': 'application/json' },
    }
  );
}

describe('staff authentication repository', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('将医护数字主键和工号映射为前端用户', () => {
    const user = mapStaffUser({
      staff: {
        id: 7,
        staff_no: 'N007',
        staff_name: '测试护士',
        role_code: 'nurse',
        department_name: '测试病区',
      },
    });

    expect(user).toMatchObject({
      id: '7',
      username: 'N007',
      role: 'nurse',
      name: '测试护士',
      department: '测试病区',
    });
  });

  it('API 模式登录发送工号密码且携带会话凭据', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        staff: {
          id: 1,
          staff_no: 'N001',
          staff_name: '李护士',
          role_code: 'nurse',
          department_name: '心内科',
        },
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const user = await new ApiCareRepository().loginStaff({
      staffNo: 'N001',
      password: '123456',
    });

    const [url, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/auth/staff/login');
    expect(request.credentials).toBe('include');
    expect(JSON.parse(String(request.body))).toEqual({
      staff_no: 'N001',
      password: '123456',
    });
    expect(user.id).toBe('1');
    expect(user.username).toBe('N001');
  });

  it('API 模式从医护任务接口读取历史任务', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse([
        {
          task_id: 109,
          task_no: 'TASK-HISTORY-109',
          session_id: 'SESS-HISTORY-109',
          patient_id: 1,
          encounter_id: 2,
          patient_name: '周海燕',
          bed_no: '09-1',
          collection_mode: 'ai_dialogue',
          task_status: 'pending_review',
          created_at: '2026-08-19T10:00:00Z',
        },
      ])
    );
    vi.stubGlobal('fetch', fetchMock);

    const tasks = await new ApiCareRepository().listMyTasks();

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/tasks'),
      expect.objectContaining({ credentials: 'include' })
    );
    expect(tasks[0]).toMatchObject({
      id: '109',
      taskNo: 'TASK-HISTORY-109',
      patientName: '周海燕',
    });
  });

  it('患者任务刷新使用患者专用接口，不依赖医护会话', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse([
        {
          task_id: 111,
          task_no: 'TASK-PATIENT-111',
          session_id: 'SESS-PATIENT-111',
          patient_id: 1,
          encounter_id: 2,
          patient_name: '张桂芳',
          bed_no: '01-1',
          collection_mode: 'ai_dialogue',
          task_status: 'in_progress',
          created_at: '2026-08-20T10:00:00Z',
        },
      ])
    );
    vi.stubGlobal('fetch', fetchMock);

    const tasks = await new ApiCareRepository().listPatientTasks();

    const [url, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/patients/me/tasks');
    expect(url).not.toMatch(/\/api\/tasks(?:$|\?)/);
    expect(request.credentials).toBe('include');
    expect(tasks[0]).toMatchObject({
      id: '111',
      patientName: '张桂芳',
    });
  });

  it('医护端重试首问准备使用原任务接口', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      okResponse({
        task_id: 112,
        task_no: 'TASK-RETRY-112',
        patient_id: 1,
        encounter_id: 2,
        patient_name: '张桂芳',
        bed_no: '01-1',
        collection_mode: 'ai_dialogue',
        task_status: 'in_progress',
        preparation: {
          status: 'queued',
          stage: 'schedule_prepare',
          attempt: 2,
          stages: {},
        },
        created_at: '2026-08-20T10:00:00Z',
      })
    );
    vi.stubGlobal('fetch', fetchMock);

    const task = await new ApiCareRepository().retryTaskPreparation('112');

    const [url, request] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain('/api/tasks/112/preparation/retry');
    expect(request.method).toBe('POST');
    expect(task.preparation?.status).toBe('queued');
    expect(task.preparation?.attempt).toBe(2);
  });

  it('Mock 模式支持多组演示医护账号并拒绝错误密码', async () => {
    const repository = new MockCareRepository();

    await expect(
      repository.loginStaff({ staffNo: 'N004', password: '123456' })
    ).resolves.toMatchObject({
      id: 'N004',
      name: '陈护士',
    });
    await expect(
      repository.loginStaff({ staffNo: 'N004', password: 'wrong' })
    ).rejects.toThrow('工号或密码错误');
  });
});
