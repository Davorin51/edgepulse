# Next engineering milestones

1. Verify agent collectors on actual Raspberry Pi and Jetson; record OS/kernel/sensor identity.
2. Authenticate dashboard reads and introduce per-device enrollment and token rotation.
3. Design a separate historical ingestion path before adding durable offline buffering; historical
   samples must never reset current liveness. Latest-sample retry/backoff is implemented in v0.2.0.
4. Run Docker/Compose and the provided CI on actual target machines.
5. Automate browser fault, offline timeout, recovery and export scenarios at mobile widths.
6. Add optional Jetson GPU collectors only when actual counters can be verified.
7. Explore a separate FPGA UART counter collector with a documented hardware interface.

No remote arbitrary command execution or public management endpoint is planned by default.
