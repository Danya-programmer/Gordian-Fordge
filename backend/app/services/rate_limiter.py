from datetime import datetime, timedelta


class RateLimiter:
    def __init__(self, max_requests: int = 20, time_window: int = 60):
        self.max_requests = max_requests
        self.time_window = time_window
        self.requests = []

    def can_make_request(self) -> bool:
        now = datetime.now()
        self.requests = [t for t in self.requests if now - t < timedelta(seconds=self.time_window)]
        return len(self.requests) < self.max_requests

    def record_request(self):
        self.requests.append(datetime.now())

    def get_wait_time(self) -> int:
        if not self.requests:
            return 0
        now = datetime.now()
        oldest = min(self.requests)
        wait_time = self.time_window - (now - oldest).seconds
        return max(0, wait_time)
