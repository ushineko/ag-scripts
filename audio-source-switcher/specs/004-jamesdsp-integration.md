# Spec 004: JamesDSP Integration

**Status: COMPLETE**

## Description
Smart integration with JamesDSP audio effects processor via PipeWire graph manipulation.

## Requirements
- Detect JamesDSP sink presence
- Rewire JamesDSP output to selected physical device
- Handle JamesDSP crashes with circuit breaker
- Enforce routing on startup

## Acceptance Criteria
- [x] Detects JamesDSP as virtual output filter
- [x] Rewires PipeWire graph on device switch
- [x] Effects maintained during device switching
- [x] Circuit breaker detects zombie JamesDSP state
- [x] Auto-fallback to hardware on JamesDSP failure
- [x] Visual indicator "Effects Active" in UI

## Implementation Notes
PipeWire graph manipulation for JamesDSP routing. Startup enforcement claims audio for effects.
