# CardLab v2 referee card feature

`CARDLAB_FEATURES_V2` keeps the other CardLab context features from V1 and changes the referee card rate (`CARD_COUNT_RULE_V2`).

For a completed historical match with an immutable 1xBet card event observation, use its regular time card total. The observation is collected for referee history only when provider event yellow cards match the home and away yellow statistics. This permits matches whose fixture statistics omit a red card count without treating `null` as zero. For historical matches without a verified event observation, use the V1 statistics rule only when both yellow and red statistics are complete. Each match contributes at most one sample.

The feature payload records the event sample count and the calculation version. The five match minimum for CardLab decisions is unchanged. Existing V1 snapshots remain immutable.
