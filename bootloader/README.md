# Bootloader Core (Shared)

Portable boot protocol and policy core used by Project A.

## Contents

- `include/pa_boot_protocol.h`: binary layout for image header and boot state
- `include/pa_boot_policy.h`: state transition and decision API
- `src/pa_boot_policy.c`: policy implementation

## Role in final architecture

- This module defines protocol compatibility for host tools and bootloader runtime.
- Hardware-specific bootloader implementation is in `bootloader_f407/`.
- Application and host scripts read the same protocol definitions to keep upgrade flow consistent.
