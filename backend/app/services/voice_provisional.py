"""语音交流的临时跳过状态；不产生答案、评分或完成信号。"""

from dataclasses import dataclass, field


@dataclass
class VoiceProvisionalState:
    message_no: str = ""
    patient_text: str = ""
    turn: int = 0
    pending: dict[int, str] = field(default_factory=dict)
    deferred_until: dict[int, int] = field(default_factory=dict)

    def begin_turn(self, message_no: str, text: str) -> None:
        if message_no != self.message_no:
            self.turn += 1
        self.message_no, self.patient_text = message_no, text

    def mark(self, ids: list[int], quote: str, allowed: set[int]) -> None:
        if not self.message_no or not ids or not quote.strip() or quote not in self.patient_text:
            raise ValueError("初判必须引用当前患者原话，不能虚构依据")
        if any(type(i) is not int or i not in allowed for i in ids):
            raise ValueError("初判题号超出可交谈范围")
        for question_id in ids:
            self.pending[question_id] = self.message_no

    def settle(self, remaining: set[int], processed: set[str], *, expired: bool = False) -> None:
        for question_id, source in list(self.pending.items()):
            if question_id not in remaining:
                self.pending.pop(question_id)
                self.deferred_until.pop(question_id, None)
            elif source in processed or expired:
                self.pending.pop(question_id)
                self.deferred_until[question_id] = self.turn + 2
        self.deferred_until = {i: turn for i, turn in self.deferred_until.items() if i in remaining}

    def available(self, remaining: set[int]) -> set[int]:
        return {
            i
            for i in remaining
            if i not in self.pending and self.deferred_until.get(i, 0) <= self.turn
        }
