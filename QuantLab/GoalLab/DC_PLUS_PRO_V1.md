# GoalLab — DC+ Pro V1

Status: proposed implementation contract.

## Objective

DC+ Pro V1 is the first full GoalLab model intended to improve on the production
Dixon-Coles control using a **large, regularized, timestamp-safe feature pool**.

The design intentionally starts broad. We will remove variables through out-of-sample
evidence and ablation rather than artificially restricting the first candidate set.

The plain production Dixon-Coles model remains a read-only control benchmark and has no
GoalLab shadow-pick authority.

## Mathematical structure

Retain the Dixon-Coles score model and low-score correction, but augment the expected-goal
log intensities with covariates.

Conceptually:

```
log(lambda_home) =
    intercept
  + home_advantage
  + attack_home
  + defense_away
  + home_feature_offset
  + matchup_feature_offset

log(lambda_away) =
    intercept
  + attack_away
  + defense_home
  + away_feature_offset
  + matchup_feature_offset_away
```

The DC rho correction for 0-0, 0-1, 1-0 and 1-1 remains.

The additional offsets must be learned from historical data. No hand-written coefficient
may be promoted into the probability model merely because a football relationship seems
plausible.

## Model families to compare

Every training/evaluation run should produce comparable outputs for:

1. **DC Control** — existing Dixon-Coles only.
2. **DC+ Pro Structural** — football features only.
3. **DC+ Pro Late-Lineup** — Structural + target lineup/player availability.
4. **DC+ Pro Market-Aware** — Structural or Late-Lineup + bookmaker features.
5. **DC+ Pro Provider-Ensemble** — optional external /predictions block.

Structural DC+ is the primary scientific model. Market-aware/provider ensembles must never
silently replace it.

## Feature registry

All rolling features should support multiple windows when sample size permits, normally:

- last 3;
- last 5;
- last 10;
- season-to-date;
- exponentially decayed history.

Home/away splits are separate features rather than replacements for all-match form.

### A. Base Dixon-Coles parameters

1. league scoring intercept
2. home advantage
3. home team attack strength
4. home team defence strength
5. away team attack strength
6. away team defence strength
7. rho low-score dependency
8. xi recency decay
9. fitted team match count
10. fitted league match count

Counts are useful as reliability/modulation variables even when the core parameter already
exists.

### B. Recent result / goal form

11. home goals-for L3
12. home goals-for L5
13. home goals-for L10
14. home goals-against L3
15. home goals-against L5
16. home goals-against L10
17. away goals-for L3
18. away goals-for L5
19. away goals-for L10
20. away goals-against L3
21. away goals-against L5
22. away goals-against L10
23. home points-per-game L3
24. home PPG L5
25. home PPG L10
26. away PPG L3
27. away PPG L5
28. away PPG L10
29. home win rate L5/L10
30. away win rate L5/L10
31. home draw rate L5/L10
32. away draw rate L5/L10
33. home clean-sheet rate
34. away clean-sheet rate
35. home failed-to-score rate
36. away failed-to-score rate
37. home BTTS rate
38. away BTTS rate
39. home Over-2.5 rate
40. away Over-2.5 rate
41. home goal-difference trend
42. away goal-difference trend

### C. Venue-specific team form

43. home team's goals-for in home matches
44. home team's goals-against in home matches
45. home team's home PPG
46. home team's home clean-sheet rate
47. home team's home failed-to-score rate
48. away team's goals-for in away matches
49. away team's goals-against in away matches
50. away team's away PPG
51. away team's away clean-sheet rate
52. away team's away failed-to-score rate
53. home-vs-away attack differential
54. home-vs-away defensive vulnerability differential

### D. Season aggregate strength

55. home season GF/match
56. home season GA/match
57. away season GF/match
58. away season GA/match
59. home season win rate
60. away season win rate
61. home season clean-sheet rate
62. away season clean-sheet rate
63. home season failed-to-score rate
64. away season failed-to-score rate
65. home scoring rate / league scoring rate
66. away scoring rate / league scoring rate
67. home conceding rate / league average
68. away conceding rate / league average

### E. Shot production and prevention

69. home shots-for L5
70. home shots-against L5
71. away shots-for L5
72. away shots-against L5
73. home SOT-for L5
74. home SOT-against L5
75. away SOT-for L5
76. away SOT-against L5
77. total-shot differential
78. SOT differential
79. home shot share
80. away shot share
81. home SOT share
82. away SOT share
83. home shots-inside-box
84. home shots-outside-box
85. away shots-inside-box
86. away shots-outside-box
87. inside-box shot share
88. blocked-shot rate
89. shots per goal
90. goals per SOT
91. opponent goals per SOT allowed
92. rolling finishing conversion
93. rolling defensive conversion allowed
94. shot-quality proxy for home
95. shot-quality proxy for away

Items 94–95 are explicitly **proxies**, not provider-native xG.

### F. Goalkeeper / finishing interaction

96. home goalkeeper saves per match
97. away goalkeeper saves per match
98. home save percentage proxy
99. away save percentage proxy
100. home opponent SOT faced
101. away opponent SOT faced
102. finishing-vs-save interaction home
103. finishing-vs-save interaction away

### G. Possession and passing

104. home possession L5
105. away possession L5
106. possession differential
107. home passes L5
108. away passes L5
109. home accurate passes L5
110. away accurate passes L5
111. home pass accuracy
112. away pass accuracy
113. pass-volume differential
114. pass-accuracy differential
115. possession-adjusted shot production
116. possession-adjusted SOT production
117. control/territorial proxy

### H. Set pieces / territory

118. home corners-for L5
119. home corners-against L5
120. away corners-for L5
121. away corners-against L5
122. corner differential
123. corner share
124. offsides-for
125. offsides-against
126. offensive-territory proxy
127. set-piece-pressure proxy

### I. Discipline / game-state tendencies

128. fouls committed L5
129. fouls drawn proxy where derivable
130. yellow cards L5
131. red-card rate
132. opponent card rate
133. historical red-card match frequency
134. penalty-event frequency
135. penalty conceded frequency

These features require careful treatment because cards/red cards can be consequences of
game state rather than pure pre-match causal drivers.

### J. Rest and congestion

136. home days since previous match
137. away days since previous match
138. rest-day differential
139. home matches last 7 days
140. away matches last 7 days
141. home matches last 14 days
142. away matches last 14 days
143. home matches last 21 days
144. away matches last 21 days
145. congestion differential
146. home consecutive away-match count
147. away consecutive away-match count
148. home short-rest flag
149. away short-rest flag
150. both-teams-short-rest interaction

### K. Standings / competitive context

151. home rank
152. away rank
153. rank differential
154. home points
155. away points
156. points differential
157. home PPG
158. away PPG
159. PPG differential
160. home goal difference
161. away goal difference
162. goal-difference differential
163. home rank percentile
164. away rank percentile
165. distance to first/title
166. distance to promotion/continental threshold
167. distance to relegation threshold
168. home table pressure
169. away table pressure
170. match importance
171. both-teams-high-pressure interaction

### L. Injury / suspension availability

172. home unavailable-player count
173. away unavailable-player count
174. unavailable-count differential
175. home injury count
176. away injury count
177. home suspension count
178. away suspension count
179. home regular-starter absences
180. away regular-starter absences
181. home missing-minutes share
182. away missing-minutes share
183. home missing-goals share
184. away missing-goals share
185. home missing-assists share
186. away missing-assists share
187. home missing-attacking-contribution score
188. away missing-attacking-contribution score
189. home missing-defensive-contribution score
190. away missing-defensive-contribution score
191. home goalkeeper-unavailable flag
192. away goalkeeper-unavailable flag
193. availability-strength differential

### M. Target lineup / formation — late layer

194. home regular starters present
195. away regular starters present
196. home XI continuity vs previous match
197. away XI continuity
198. XI continuity differential
199. home average XI season minutes
200. away average XI season minutes
201. home XI goals contribution
202. away XI goals contribution
203. home XI assists contribution
204. away XI assists contribution
205. home XI average recent rating
206. away XI average recent rating
207. lineup-strength differential
208. home formation
209. away formation
210. home formation changed
211. away formation changed
212. attacking-shape indicator
213. defensive-shape indicator
214. bench-depth score
215. lineup availability confidence

Formation itself should be encoded categorically, not treated as an ordinal number.

### N. Player-form aggregation

216. projected home XI rolling rating
217. projected away XI rolling rating
218. projected home XI shots/SOT
219. projected away XI shots/SOT
220. projected home XI key passes
221. projected away XI key passes
222. projected home XI goals+assists per 90
223. projected away XI goals+assists per 90
224. home defensive actions per 90
225. away defensive actions per 90
226. home duel-win profile
227. away duel-win profile
228. home creator concentration
229. away creator concentration
230. home scorer concentration
231. away scorer concentration
232. player-quality differential

### O. Manager / coaching context

233. home manager tenure days
234. away manager tenure days
235. home matches under manager
236. away matches under manager
237. home recent-manager-change flag
238. away recent-manager-change flag
239. manager-tenure differential
240. both-new-manager interaction

### P. H2H block

241. H2H goals/match L3
242. H2H goals/match L5
243. H2H BTTS rate
244. H2H Over-2.5 rate
245. H2H home-team goals
246. H2H away-team goals
247. H2H goal difference
248. H2H recency-weighted result score
249. H2H sample size
250. H2H age/recency quality

H2H sample size and age must regularize the block toward zero influence when evidence is
weak.

### Q. Opponent-adjusted form

251. home attack form adjusted for opponent defensive strength
252. away attack form adjusted for opponent defensive strength
253. home defence form adjusted for opponent attack strength
254. away defence form adjusted for opponent attack strength
255. home SOT form adjusted for opponent SOT prevention
256. away SOT form adjusted for opponent SOT prevention
257. strength-of-schedule home
258. strength-of-schedule away
259. schedule-strength differential

### R. Matchup interaction features

260. home recent attack × away recent defensive weakness
261. away recent attack × home recent defensive weakness
262. home SOT production × away SOT allowed
263. away SOT production × home SOT allowed
264. home finishing × away save weakness
265. away finishing × home save weakness
266. home possession × away low-possession profile
267. away possession × home low-possession profile
268. home rest advantage × away congestion
269. away rest advantage × home congestion
270. home missing attackers × away defence strength
271. away missing attackers × home defence strength
272. home lineup strength × away defensive availability
273. away lineup strength × home defensive availability
274. table-pressure differential × season progress

Interactions should be constrained/regularized more strongly than base features.

## Optional market-aware block

These variables are **not** structural DC+ Core.

275. Bet365 de-vig Over 2.5 probability
276. 1xBet de-vig Over 2.5 probability
277. market consensus Over 2.5
278. bookmaker disagreement Over 2.5
279. Bet365 de-vig BTTS probability
280. 1xBet de-vig BTTS probability
281. market consensus BTTS
282. bookmaker disagreement BTTS
283. opening-to-current price movement
284. line movement
285. market age/freshness
286. bookmaker availability count

Use this block only in `DC_PLUS_PRO_MARKET_AWARE_V1`.

## Optional provider-prediction ensemble block

Also separate from Structural DC+:

287. provider predicted home goals
288. provider predicted away goals
289. provider Over/Under signal
290. provider home-win percentage
291. provider draw percentage
292. provider away-win percentage
293. provider attack comparison
294. provider defence comparison
295. provider Poisson comparison
296. provider form comparison
297. provider H2H comparison

Use only in `DC_PLUS_PRO_PROVIDER_ENSEMBLE_V1`.

## Missingness features

Coverage itself can contain signal and must be explicit rather than silently imputed.

For major blocks store:

- feature available flag;
- sample count;
- last observation age;
- coverage quality;
- imputation strategy/version.

Examples:

298. fixture-stats coverage flag
299. lineup coverage flag
300. injury coverage flag
301. player-stats coverage flag
302. standings coverage flag
303. H2H sample-size flag
304. feature snapshot age
305. team-history sample size

Missing values may be:

- shrinkage-to-league mean;
- model-native missing;
- explicit missing indicator + conservative imputation.

No zero-as-missing convention is allowed.

## Training strategy

### 1. Freeze timestamp-safe dataset

For every historical target fixture, reconstruct only facts available at the chosen
decision timestamp.

Suggested decision checkpoints:

- T-24h structural;
- T-6h structural refresh;
- T-90m availability refresh;
- T-30m lineup/late model when lineups exist.

### 2. Learn covariate offsets jointly with DC

Preferred first implementation:

- retain team attack/defence random/fixed effects;
- regularized linear covariate offsets on log goal intensities;
- strong ridge/elastic-net regularization;
- standardized numeric features;
- categorical encodings for formation/competition context where justified;
- explicit missing indicators;
- no manual football coefficient values.

More flexible nonlinear models may later predict residual goal-intensity offsets, but they
must benchmark against the interpretable regularized DC+ first.

### 3. Hierarchical shrinkage

Broad league coverage requires shrinkage.

Use:

- league-level baseline;
- team attack/defence shrinkage;
- feature normalization by league/season where appropriate;
- minimum sample weighting;
- optional country/competition random effects.

Do not let a five-match obscure-league sample produce the same parameter confidence as a
large mature league sample.

### 4. Feature selection by evidence, not by initial scarcity

Start with the broad registry, then evaluate:

- coefficient stability;
- multicollinearity;
- out-of-sample log loss;
- Brier score;
- calibration;
- likelihood improvement;
- CLV;
- flat-stake ROI;
- league robustness;
- temporal robustness.

Drop variables/blocks that fail out-of-sample contribution.

## Evaluation matrix

Every DC+ Pro release should report at minimum:

- DC Control vs DC+ Structural;
- DC+ Structural vs Late-Lineup;
- structural vs Market-Aware;
- bookmaker split;
- league split;
- season/time split;
- O/U 2.5;
- BTTS;
- calibration bins;
- log loss;
- Brier;
- CLV;
- ROI/yield;
- max drawdown;
- sample size.

A profitable market-aware ensemble does not prove Structural DC+ is better. Those results
must remain separately labeled.

## Leakage rules

Forbidden for a target pre-match prediction:

- target final score;
- target post-kickoff events;
- target post-kickoff fixture statistics;
- target post-kickoff player stats;
- lineups captured after the model decision timestamp;
- injuries/standings snapshots acquired after decision time;
- closing odds if prediction is meant to represent an earlier checkpoint.

Every feature row must retain:

- source endpoint;
- raw observation identity/hash;
- available_at;
- target fixture;
- feature version;
- calculation version;
- sample window;
- quality/missingness metadata.

## Acquisition priorities under 75k/day

The expanded budget allows broad acquisition, but requests should still be useful.

Priority:

1. global fixture discovery;
2. all-market odds across the upcoming universe;
3. league/season coverage metadata cache;
4. historical fixture statistics backfill;
5. team season statistics;
6. target injuries/suspensions where covered;
7. standings;
8. player historical stats needed for availability/lineup strength;
9. target lineups near kickoff;
10. H2H;
11. manager context;
12. provider predictions only for separately labeled ensemble research.

## Pick authority

DC Control: **no GoalLab PICK authority**.

DC+ Pro Structural / Late-Lineup may gain shadow-pick authority only after:

- the model artifact is versioned;
- feature provenance passes leakage audit;
- holdout/backtest metrics are recorded;
- the decision policy is separately versioned.

No experiment may write production registered picks or bankroll state.
