-- 仅用于演示环境，精确更新测试账号旧名，不改密码、权限或历史报告。
BEGIN;
UPDATE staff_account SET staff_name = '李白'
WHERE staff_no = 'N001' AND staff_name IN ('李护士', '李某') AND deleted = 0;
SELECT staff_no, staff_name FROM staff_account WHERE staff_no = 'N001' AND deleted = 0;
COMMIT;
