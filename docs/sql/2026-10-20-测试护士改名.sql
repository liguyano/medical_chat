-- 仅用于演示环境：精确修改 N001 的旧显示名，不修改密码、权限及历史记录。
BEGIN;
UPDATE staff_account
SET staff_name = '李某'
WHERE staff_no = 'N001' AND staff_name = '李护士' AND deleted = 0;
SELECT staff_no, staff_name FROM staff_account WHERE staff_no = 'N001' AND deleted = 0;
COMMIT;
