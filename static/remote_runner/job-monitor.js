import { STATUS_POLL_INTERVAL_MS } from "./config.js";

export class JobMonitor {
  constructor({ fetchHistory, onUpdate, onError }) {
    this.fetchHistory = fetchHistory;
    this.onUpdate = onUpdate;
    this.onError = onError;
    this.timer = null;
  }

  stop() {
    if (this.timer) {
      window.clearTimeout(this.timer);
      this.timer = null;
    }
  }

  async start({ baseUrl, promptId }) {
    this.stop();

    const tick = async () => {
      try {
        const payload = await this.fetchHistory(baseUrl, promptId);
        this.onUpdate(payload);

        if (payload.status === "success" || payload.status === "failed") {
          this.stop();
          return;
        }

        this.timer = window.setTimeout(tick, STATUS_POLL_INTERVAL_MS);
      } catch (error) {
        this.onError(error);
      }
    };

    await tick();
  }
}

