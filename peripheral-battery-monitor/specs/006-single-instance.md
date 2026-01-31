# Spec 006: Single Instance Enforcement

**Status: COMPLETE**

## Description
Prevent multiple instances of the application running.

## Requirements
- Use QLockFile for single instance check
- Dynamic battery status icons in UI

## Acceptance Criteria
- [x] QLockFile prevents duplicate instances
- [x] Battery status icons update dynamically
- [x] Worker thread overlap prevented

## Implementation Notes
Added in v1.1.1. Prevents resource issues from multiple instances.
