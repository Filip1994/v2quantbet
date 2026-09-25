-- QuantBet research/shadow signals: durable exposure-blocked evidence without bankroll effects.

ALTER TABLE value_evaluations
    ADD CONSTRAINT value_evaluations_research_fixture_key
    UNIQUE (evaluation_id, fixture_id);

CREATE TABLE research_signals (
    signal_id TEXT PRIMARY KEY
        CHECK (signal_id ~ '^research-signal-v1:[0-9a-f]{64}$'),
    evaluation_id TEXT NOT NULL UNIQUE,
    fixture_id TEXT NOT NULL,
    blocked_at TIMESTAMPTZ NOT NULL,
    blocked_stage TEXT NOT NULL
        CHECK (blocked_stage IN ('PRELIMINARY_RISK', 'FINAL_RISK')),
    reason_codes TEXT[] NOT NULL,
    capture_method TEXT NOT NULL
        CHECK (capture_method IN ('LIVE_V1', 'LOG_BACKFILL_V1')),
    policy_fingerprint TEXT,
    policy_configuration JSONB,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (evaluation_id, fixture_id)
        REFERENCES value_evaluations(evaluation_id, fixture_id) ON DELETE RESTRICT,
    CHECK (
        cardinality(reason_codes) = 1
        AND reason_codes[1] = 'MAX_OPEN_EXPOSURE_EXCEEDED'
    ),
    CHECK (
        (capture_method = 'LIVE_V1'
            AND policy_fingerprint IS NOT NULL
            AND policy_configuration IS NOT NULL)
        OR
        (capture_method = 'LOG_BACKFILL_V1')
    )
);

CREATE INDEX idx_research_signals_fixture
    ON research_signals (fixture_id, blocked_at, signal_id);
CREATE INDEX idx_research_signals_blocked
    ON research_signals (blocked_at DESC, signal_id);

CREATE TABLE research_fixture_result_finalizations (
    fixture_id TEXT PRIMARY KEY REFERENCES fixtures(fixture_id) ON DELETE RESTRICT,
    result_observation_id TEXT NOT NULL,
    settlement_fingerprint TEXT NOT NULL CHECK (length(trim(settlement_fingerprint)) > 0),
    finalized_at TIMESTAMPTZ NOT NULL,
    method_version TEXT NOT NULL
        CHECK (method_version = 'RESEARCH_RESULT_FINALIZATION_V1'),
    FOREIGN KEY (result_observation_id, fixture_id)
        REFERENCES fixture_result_observations(result_observation_id, fixture_id)
        ON DELETE RESTRICT
);

CREATE INDEX idx_research_result_finalized
    ON research_fixture_result_finalizations (finalized_at, fixture_id);

CREATE FUNCTION reject_research_fact_mutation() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'research signal facts are append-only';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER research_signals_append_only
    BEFORE UPDATE OR DELETE ON research_signals
    FOR EACH ROW EXECUTE FUNCTION reject_research_fact_mutation();

CREATE TRIGGER research_fixture_results_append_only
    BEFORE UPDATE OR DELETE ON research_fixture_result_finalizations
    FOR EACH ROW EXECUTE FUNCTION reject_research_fact_mutation();

-- Backfill exact exposure-only preliminary evaluations recovered by pairing the
-- opportunity rejection event with its risk event (<= 5 ms in captured logs).
WITH seed(evaluation_id, blocked_at) AS (
    VALUES
    ('value-evaluation-v1:86979c9cb316a6db577456277b8d28251889c992afbe28fb3c9473028bd872ac', '2026-09-24T17:41:32.415436+00:00'::timestamptz),
    ('value-evaluation-v1:2ba9fda50040c2c0fb415843b094677cc2e33d5a9fc9cf30e18599a97ebc40bf', '2026-09-24T17:41:32.452208+00:00'::timestamptz),
    ('value-evaluation-v1:aa4f51a110b465402206f0e14b43bfd09bb16d9678957f763009cdf9c1b0f593', '2026-09-24T17:46:44.989108+00:00'::timestamptz),
    ('value-evaluation-v1:6d2ac6c6548c57238e0f5dfdcb1202ab0c7b547473e217425e9e6c4078ceea91', '2026-09-24T17:46:45.027063+00:00'::timestamptz),
    ('value-evaluation-v1:243a59c929ba54ea30dc42fcd237a6d447d2cf5d353eb3ac96d0b0fed5136d5f', '2026-09-24T17:46:45.100006+00:00'::timestamptz),
    ('value-evaluation-v1:f9967d023e89245409a68df42a72e016718434bd9bacd109f799b10a316ac89b', '2026-09-24T17:46:45.068965+00:00'::timestamptz),
    ('value-evaluation-v1:241cb41b84a8d2ab3701594547fec14eb2472bf2a6ba90a8b1e04d56e63348e7', '2026-09-24T17:47:48.408124+00:00'::timestamptz),
    ('value-evaluation-v1:fe7d9d945bb7d36e398dd4b723e3108e546d378b04136902373809a4472b5e70', '2026-09-24T17:47:48.438763+00:00'::timestamptz),
    ('value-evaluation-v1:e353f2c8e87883880a0bf1bb1a50210f9fcc57228d5beea03997a3e5a6a59ece', '2026-09-24T17:49:59.568516+00:00'::timestamptz),
    ('value-evaluation-v1:2aa716ad8bcd8667f2d5bc6abb14b05db92581d086e5e0981b148a17c13b9b78', '2026-09-24T17:49:59.599602+00:00'::timestamptz),
    ('value-evaluation-v1:3a7d86ea9f9b6dbcc4f30f30fd19b90f97a87be823a77735cbe1cc23191d673b', '2026-09-24T17:49:59.630078+00:00'::timestamptz),
    ('value-evaluation-v1:3256131fc90729a391013c9c06fe2e658db508f45355677ba5c9617ebe877f51', '2026-09-24T17:51:04.090814+00:00'::timestamptz),
    ('value-evaluation-v1:cee34c339fc33d0d10c6fbe9330f85f09292f8bc7f8ee7f80f11f61844e0d89e', '2026-09-24T17:51:04.123901+00:00'::timestamptz),
    ('value-evaluation-v1:9c7758f182485682ed3cb8e8350d740bb66636c554913e0c798399040493fd64', '2026-09-24T17:51:04.166102+00:00'::timestamptz),
    ('value-evaluation-v1:561678aed2659ba5628542052acbbc2abd4dad726d95cf83a2212a81c379450b', '2026-09-24T17:51:04.289402+00:00'::timestamptz),
    ('value-evaluation-v1:b01e14bfadc308466a27f4d768194caefb461248aaf5d593cf25246ae6d0b603', '2026-09-24T17:52:10.899260+00:00'::timestamptz),
    ('value-evaluation-v1:3be37dea2dc2fa223e0d9728396ddfd84f640db3c5c46655c8bd67f2b15743af', '2026-09-24T17:52:10.940254+00:00'::timestamptz),
    ('value-evaluation-v1:2f65139e2888cf972e30b6374834471a2bbc303b1ea427cf3f8d79934a6374cc', '2026-09-24T17:52:12.539906+00:00'::timestamptz),
    ('value-evaluation-v1:d0105275159cd6d305c45ee7df692a595d9c654f1d76b9588cc4be1c15720363', '2026-09-24T17:52:12.575565+00:00'::timestamptz),
    ('value-evaluation-v1:78a9e710de6ad5f6568cf19b2976f1260d290ea9bbd0e1edb520def20fc01c0f', '2026-09-24T17:56:27.244923+00:00'::timestamptz),
    ('value-evaluation-v1:8dc23a51360f9a036f766b9bfd70f697b6927c1c7ab8ac2464bebac1e147780a', '2026-09-24T17:56:27.281970+00:00'::timestamptz),
    ('value-evaluation-v1:4c5214f8d3bf7c95b2737320f13b0f83e73648facc841038f24bb8c8192031f8', '2026-09-24T17:56:27.315461+00:00'::timestamptz),
    ('value-evaluation-v1:489ea099df5735ee18f10e5d23ea1d91ba17d57f9945aed16c5232550dda2a2d', '2026-09-24T17:56:28.780134+00:00'::timestamptz),
    ('value-evaluation-v1:390804d2b61a750065943412b2721738f2913fda084d904816009b0b6bb71a61', '2026-09-24T17:56:28.812416+00:00'::timestamptz),
    ('value-evaluation-v1:db30df23f6ddc9c03c256602a9ff473293f4b3bdfcb21e5fb737cc2332889fc4', '2026-09-24T18:03:59.540447+00:00'::timestamptz),
    ('value-evaluation-v1:a5b2bb70221fa53ca8d475857b65e97a163419c3d52fd2f2d203c34e57872197', '2026-09-24T18:04:01.381866+00:00'::timestamptz),
    ('value-evaluation-v1:1021dfeaadf7fc703e88fc9c80685c5904533a6aa331323c7736073b761bd2c6', '2026-09-24T18:04:01.426283+00:00'::timestamptz),
    ('value-evaluation-v1:cffe38ad04bbcb3f18d07bba4416d1bfa5358f4d5ef18d9553fa26c6ea5058d1', '2026-09-24T18:04:01.466738+00:00'::timestamptz),
    ('value-evaluation-v1:42f32ba35a42ce17dc756507950f929419b9256b6e1f10cfb72b080627e91c62', '2026-09-24T18:04:01.502616+00:00'::timestamptz),
    ('value-evaluation-v1:47644e7249d4fcb4bc2732d6e9bb2e64ef6a97db755bd86a2dbb58aec7ee58dc', '2026-09-24T18:05:06.864635+00:00'::timestamptz),
    ('value-evaluation-v1:580e15bc3807a2b26cb6a80c8c1ecadbca6ee9605f3119305a519e8bb2634bee', '2026-09-24T18:05:06.910325+00:00'::timestamptz),
    ('value-evaluation-v1:a6ce420df1652aa78447dcb8772a1d3042cb691f08a43dea2c97e52a89f63383', '2026-09-24T18:05:06.965309+00:00'::timestamptz),
    ('value-evaluation-v1:2376fb601b783f56f0491107e910a6545546f6af0eb3f162bba510902c48aaeb', '2026-09-24T18:05:07.013708+00:00'::timestamptz),
    ('value-evaluation-v1:43fcda89afbe62427f0e0a93d3d93bfbf8fcf2c636d4b5b1754635d74d177eb4', '2026-09-24T18:06:14.038882+00:00'::timestamptz),
    ('value-evaluation-v1:c35b942b9771c2a83d4c4a62bcf3556e2e9d2cd2362bde6faf84061430ed9702', '2026-09-24T18:09:28.080944+00:00'::timestamptz),
    ('value-evaluation-v1:b9c32d799f409252119d373c3a74b2ee05ab3d52cb3a684c700270eb8348bd8e', '2026-09-24T18:10:29.347007+00:00'::timestamptz),
    ('value-evaluation-v1:6588fac7776d824a626fb5badc430760c0c3256e09678760d8fc76d66d31127b', '2026-09-24T18:10:29.369487+00:00'::timestamptz),
    ('value-evaluation-v1:5dd49071abdfe007fa17ec5d3a932539a01e1e6bb0336a85f8b001a681cd03b5', '2026-09-24T18:10:29.390003+00:00'::timestamptz),
    ('value-evaluation-v1:4a7d8120c2e6d4e0f5fa315c5668102308bf20cef28c4d83a671c17a30161059', '2026-09-24T18:14:49.217450+00:00'::timestamptz),
    ('value-evaluation-v1:0b9ec7402a59e198982474c6f6b1c0df3bdc8c55e3e81ecc2a984dad99360c67', '2026-09-24T18:14:49.240615+00:00'::timestamptz),
    ('value-evaluation-v1:a8edb6eecd2531118ed1082d5aa533288a592e8971ffea611585ca2010ca8259', '2026-09-24T18:15:53.962208+00:00'::timestamptz),
    ('value-evaluation-v1:ec23e9c1dcf6b49055a0739c8baff5391f5d609bfcc853cc08b6fbb343d58f4c', '2026-09-24T18:15:53.983104+00:00'::timestamptz),
    ('value-evaluation-v1:bdf780ce40d45d110667b273aafd7135218051d96cac6b0dd2669f4b06f33e3a', '2026-09-24T18:15:54.021724+00:00'::timestamptz),
    ('value-evaluation-v1:b4f5c87cc7d4153220f70811c3774e8f15936bfaf27313f4de279666f4f354c1', '2026-09-24T18:15:55.206558+00:00'::timestamptz),
    ('value-evaluation-v1:1e465470251020261f7426b7b42ca14e0e352d1a748f645d6463dc182a6c569a', '2026-09-24T18:15:55.239774+00:00'::timestamptz),
    ('value-evaluation-v1:fb7b8e9fc61692d7771933ea9f5ed4aa6c8b475cc5ec2ed0a7d11f12b24aaa4c', '2026-09-24T18:15:55.262954+00:00'::timestamptz),
    ('value-evaluation-v1:71c71ef6b4a60af194b8e5b7cf16d69d6848371e41ae03b4f9da555a2dcf8d2d', '2026-09-24T18:15:55.286790+00:00'::timestamptz),
    ('value-evaluation-v1:f190a2db36f9a74027d891169ea36d3008af0f3fb3da76713bf44a9e698d1381', '2026-09-24T18:17:01.449711+00:00'::timestamptz),
    ('value-evaluation-v1:b9d7c1483b4e8e9d34fd79b7ca6d225a34d6f7bd505de142aa8b26d16114973a', '2026-09-24T18:17:01.470403+00:00'::timestamptz),
    ('value-evaluation-v1:dae363e37e565646dfdcbe2a6c303b7ba503c44db3224209686c9908d6139635', '2026-09-24T18:17:01.490972+00:00'::timestamptz),
    ('value-evaluation-v1:e754075f9e6a948fcc33b25b16103367fbb158a997867e00293a8ee52675625b', '2026-09-24T18:17:01.513177+00:00'::timestamptz),
    ('value-evaluation-v1:3a12c1ac3ccf57f93971a3f553817bb15803473e037d5c7047907fd81b607e44', '2026-09-24T18:21:15.646246+00:00'::timestamptz),
    ('value-evaluation-v1:dfdec5ae6abe4891506aae1e9256d0812bd667835249b4280f3dd2a00962e4fa', '2026-09-24T18:21:15.669955+00:00'::timestamptz),
    ('value-evaluation-v1:34c044de068a5cccacdf3682879a1af0587665b47ac47329794d135ac7da7a94', '2026-09-24T18:21:15.689493+00:00'::timestamptz),
    ('value-evaluation-v1:6bfe93e3038a2bc3a622dc90f6e26f147a82cfba36196f88df4a01427e98d205', '2026-09-24T18:21:15.710559+00:00'::timestamptz),
    ('value-evaluation-v1:b6e850eb6af338f476f1bd073838a5e3dd363961d668150a306617e7eed8bacb', '2026-09-24T18:27:29.057725+00:00'::timestamptz),
    ('value-evaluation-v1:45b5da7a60b2ac9c48abdd0d957defc11673fddfdf06995b2652aac7987a7691', '2026-09-24T18:27:29.078106+00:00'::timestamptz),
    ('value-evaluation-v1:8892b7979901fe55e650515e418e46c75bc7e4bd63f121af38a9b0571d3ddd4b', '2026-09-24T18:33:43.564529+00:00'::timestamptz),
    ('value-evaluation-v1:9619d84ddf22a0e0581ea0ccb523e6025804444d14f9cbcff08c561c511f65ca', '2026-09-24T18:43:17.250811+00:00'::timestamptz),
    ('value-evaluation-v1:af4e478f000883c9e03a90e7fc9d961223276068dc057ff0e3161cbb5b86d0d5', '2026-09-24T18:43:17.272258+00:00'::timestamptz),
    ('value-evaluation-v1:eba3737b62f0611cb203c41d14b4655bb557bdf89e5b033c7eeada0340489f36', '2026-09-24T18:57:59.336213+00:00'::timestamptz),
    ('value-evaluation-v1:d68306d106f921fd5833f774a060385ad7e949d95bc726c9c193aaff028d1ef7', '2026-09-24T18:57:59.356824+00:00'::timestamptz),
    ('value-evaluation-v1:adaa8a0b0863a960289be6f95c262fe0b6d88894183baba1b76f5ee0a90ac109', '2026-09-24T19:19:05.085601+00:00'::timestamptz),
    ('value-evaluation-v1:36c33450f89cbff56443080bab7b239ddf333d1a271280310a8fa7cbbe009acc', '2026-09-24T19:29:25.745973+00:00'::timestamptz),
    ('value-evaluation-v1:2d98d48d054cc5fcb9ef62127461f4abb2eb76e38de2c8fedf6011a6a9d5a8c6', '2026-09-24T19:30:27.098691+00:00'::timestamptz),
    ('value-evaluation-v1:5f272be9b3bab99be1068d71a80e5e172988d207ad0e465628bfdb12fa2af553', '2026-09-24T19:32:31.131378+00:00'::timestamptz),
    ('value-evaluation-v1:6567ee4b86132c27713004546f92aa826993b0151de8f6aedc0226ccbd5a327f', '2026-09-24T19:32:31.152092+00:00'::timestamptz),
    ('value-evaluation-v1:83c9c2ce9fddbcbb395f424f2bc24dc48b43a29f70ffd275650dafa3d60b0213', '2026-09-24T20:03:54.801096+00:00'::timestamptz),
    ('value-evaluation-v1:3821dfb78be448fb5885221deba5d36bfe2eafc0f53305a9ed15c9e82953b3a1', '2026-09-24T20:03:54.833800+00:00'::timestamptz),
    ('value-evaluation-v1:0941241403643a4ae20a42d85eb1d429c51b4ad2dba30895e10719856df0577a', '2026-09-24T20:03:54.857651+00:00'::timestamptz),
    ('value-evaluation-v1:04e92596c12bb8eeb0938d20db1a1b106f78e000b5768c1daa8c161254e152c9', '2026-09-24T20:03:54.883163+00:00'::timestamptz),
    ('value-evaluation-v1:b8ed1ca5233e83ed2ed7f98e4caf28e5513cd37fdecbca32e0a57693509577ef', '2026-09-24T20:09:14.558357+00:00'::timestamptz),
    ('value-evaluation-v1:c4684f13a4e989dbc578938227ec5061e4a713a70e1acec38eb7045aab0dfc5d', '2026-09-24T20:09:15.229618+00:00'::timestamptz),
    ('value-evaluation-v1:4ba33dc1a6967a5f85c7d7dee5bb68fa5a078036a937dad3ef1924741a530d2b', '2026-09-24T20:09:15.255575+00:00'::timestamptz),
    ('value-evaluation-v1:7179b267007b673ed5a8d95f6f72a387f35b7202d40a8239ebb9fafbdb5f98be', '2026-09-24T20:10:19.804049+00:00'::timestamptz),
    ('value-evaluation-v1:5ef18aa81685135a05d62832f0014dfd63d10dce9679a7c64e5058f198c86933', '2026-09-24T20:10:19.831121+00:00'::timestamptz),
    ('value-evaluation-v1:912a7cbcea0cb6dac43c74374b0f0ab742a3f4d0efc67e80d97d6374d988a8be', '2026-09-24T20:11:25.826802+00:00'::timestamptz),
    ('value-evaluation-v1:21293908e5b2afe625e275c54eeab34ca492b0d0e844e3c46a7216eba3499438', '2026-09-24T20:16:52.244055+00:00'::timestamptz),
    ('value-evaluation-v1:30fbb0fa22b9ff13590ac96540b69ce0f98fd1257e4b63d33ad917f2b984e3a2', '2026-09-24T20:16:52.265486+00:00'::timestamptz),
    ('value-evaluation-v1:9b50167d04c780f888bc97f5563d4631d9db70a1d2331a6e1cd614399c81c681', '2026-09-24T22:21:54.109341+00:00'::timestamptz),
    ('value-evaluation-v1:c75e94be0c6f48d227bc855f0d803686398fbf7712cfacfef9046c50cf68cbd1', '2026-09-24T22:21:54.132688+00:00'::timestamptz),
    ('value-evaluation-v1:7300c364237ad5c338512577c101350b4ea0c00561a5bcb8b61ca2de3b5da66e', '2026-09-24T22:21:54.154889+00:00'::timestamptz),
    ('value-evaluation-v1:f71c1d8c618260f691ea0777f744b96aaddfe85873635a3de19d33a7018e1343', '2026-09-24T22:22:58.412083+00:00'::timestamptz),
    ('value-evaluation-v1:39b3a7d111a7631191704543818993507e7d9c95c06a41bccc41315f0f7ce3b0', '2026-09-24T22:22:58.365228+00:00'::timestamptz),
    ('value-evaluation-v1:9c153557e31b67b44a4c37a5a443669203bf6a9f1f338e33860bc4c263a4ba79', '2026-09-24T22:22:58.387947+00:00'::timestamptz),
    ('value-evaluation-v1:6edd6fa2006150369323cdb9c0cad656cc303781aae5cf4a67458c8ae9bb44c5', '2026-09-24T22:24:00.659682+00:00'::timestamptz),
    ('value-evaluation-v1:99f7b541c0270aadaa28aa7dea99dde9ae606e057bdaba2e86e2430b4a889dfd', '2026-09-24T22:24:00.681454+00:00'::timestamptz),
    ('value-evaluation-v1:d9e8baefa8c8203d0ea89f4ab6e3c46c9be5d3dd164769502759fac3c5cd424c', '2026-09-24T22:24:00.700734+00:00'::timestamptz),
    ('value-evaluation-v1:2e6b9e83b857342edfef5ce72a1a2b1ab4ab582325227ce31d2873de5adcd257', '2026-09-24T22:26:04.475478+00:00'::timestamptz),
    ('value-evaluation-v1:9ad1b27e0ec7c2cff80ef4542c2f69d8b57f4b471897807edc33b30d0f12715e', '2026-09-24T22:26:04.504192+00:00'::timestamptz),
    ('value-evaluation-v1:c8e50f78cf2c997c407a15c0f9cc73b85a2be79139353667872e90527519f36f', '2026-09-24T22:26:04.528402+00:00'::timestamptz),
    ('value-evaluation-v1:c9c8f433af442885d671f7e04f9cd9cc30f3c3c46dfd6f9fc4fcc738574ac238', '2026-09-24T22:26:04.551385+00:00'::timestamptz),
    ('value-evaluation-v1:204203fdc5e709e468a71ca1e3ce49ea1ea6924bb7185132b3eedd5efa03abe3', '2026-09-24T22:27:06.144780+00:00'::timestamptz),
    ('value-evaluation-v1:23ae9a9581eeaf923ed79eead6f1c499f47275d93fc3ccb8d10ad88886dd6e09', '2026-09-24T22:27:06.164727+00:00'::timestamptz),
    ('value-evaluation-v1:98fbfeb51d26a5ea2dc6fe8a53f7b3ab67f98b4ee841eafae60a4c07eb25f0ea', '2026-09-24T22:33:22.549400+00:00'::timestamptz),
    ('value-evaluation-v1:81752742c7c0f591961b46852caeeb4a5c6cd5cb2240f864ef85378cc243b9c5', '2026-09-24T22:33:22.574477+00:00'::timestamptz),
    ('value-evaluation-v1:50915fdde29d6d43bccc1279a805c22673aa16aa936d1cbd45a60e73244a9fee', '2026-09-24T22:33:22.594117+00:00'::timestamptz),
    ('value-evaluation-v1:0484a2e284072a0914f5e0455d1a2d4ade3e2d0e240f3e1c2ab5038345322605', '2026-09-24T22:35:25.821468+00:00'::timestamptz),
    ('value-evaluation-v1:6505888fa8939033bfd36cc33b985b8840a1ed7378669e4cfd052fac59483b17', '2026-09-24T22:35:25.842892+00:00'::timestamptz),
    ('value-evaluation-v1:eb33f40de4352e91f4765868e333b2b111df19093d6baf1027691e1967953186', '2026-09-24T22:35:26.738705+00:00'::timestamptz),
    ('value-evaluation-v1:76216114ddfc0732dcd6705a54429f3579cfa55bdd334a3cbb044922dc2595b9', '2026-09-24T22:35:26.758831+00:00'::timestamptz),
    ('value-evaluation-v1:1577cfe48b638d0587f162b1aba75815b2f00e3ead69e3fa396e1d5e2a0ebcc2', '2026-09-24T22:37:31.453653+00:00'::timestamptz),
    ('value-evaluation-v1:0c8fb2165d3970f140c550303aae767c421f97f3e5a3b557179106814fd9f76c', '2026-09-24T22:37:31.473848+00:00'::timestamptz),
    ('value-evaluation-v1:9d912881e500498db014cf4a025b6eaa97f4ad6f7eac3269d020414b9399ad2e', '2026-09-24T22:37:31.494700+00:00'::timestamptz),
    ('value-evaluation-v1:0a94fe493d056aa9442dae9b4eedd6dab94497bfdb8505e7c2688ab0494f3fb6', '2026-09-24T22:39:39.657207+00:00'::timestamptz),
    ('value-evaluation-v1:c2b1f008feba72676c6969924030a37c14f7249bf7c24846ae2419907fa5780b', '2026-09-24T22:39:39.678027+00:00'::timestamptz),
    ('value-evaluation-v1:79ee91a66ea6be0240c734a6130710ac981f4e770d70e787987d0231b32c3a37', '2026-09-24T22:39:39.701097+00:00'::timestamptz),
    ('value-evaluation-v1:d531c7fdecedd50d49875b15e23a1420da393de93ca3fec332ff5f670ac66c6a', '2026-09-24T22:39:39.721299+00:00'::timestamptz),
    ('value-evaluation-v1:878d492aa3cdb3bac1952506e2326e67fbc7905b7f2f5b22c364dee8f6b7594b', '2026-09-24T22:40:43.869660+00:00'::timestamptz),
    ('value-evaluation-v1:798137d71dc73d1288507997b5dcfcdb3ba07bbd03eacf26ec6ae887283f900c', '2026-09-24T22:40:43.913342+00:00'::timestamptz),
    ('value-evaluation-v1:b6c8e8a4e2659ccae081353f6f923d8117f87b8e4453b8fb3fb0a9b29b43c438', '2026-09-24T23:26:51.845897+00:00'::timestamptz),
    ('value-evaluation-v1:1df5ae3c84351ee02183923ff4b68b8c1ef20dc4a3c9ca5616c2039397367fd5', '2026-09-24T23:26:51.871878+00:00'::timestamptz),
    ('value-evaluation-v1:6ecd1d674c1a8f9e1d142979eb9e6012f023f76177d26dba76ae0a2f187bf6cd', '2026-09-24T23:44:36.802114+00:00'::timestamptz),
    ('value-evaluation-v1:cde86d75407732c1557d8adec808ab5aac673c87113d4bbfea8c0aab1f6a5ebc', '2026-09-24T23:52:03.230959+00:00'::timestamptz),
    ('value-evaluation-v1:571dbd24ec63f5b1afe3d5942312d516f489ef0f5cdfb98a12d9c90d420f459d', '2026-09-24T23:52:03.251775+00:00'::timestamptz),
    ('value-evaluation-v1:5867ef3cc26f57c17250fce9f756a99cd2a92d7c5947bd95f28388d74d00969f', '2026-09-24T23:52:03.274440+00:00'::timestamptz),
    ('value-evaluation-v1:3c0a6bb9003d4e882fcee4e5a425e656c6413c9e57e89cbab8dae90876d10338', '2026-09-24T23:59:25.612794+00:00'::timestamptz),
    ('value-evaluation-v1:0d81d8799bc4b2e491ebb9bc5067068907e90933f8845b718b0bc1956a0293cd', '2026-09-24T23:59:25.637020+00:00'::timestamptz),
    ('value-evaluation-v1:f196d8ed2b81651464cbaf09d153c51439c4de3bac7b9b47e697a65f2ace4383', '2026-09-24T23:59:25.658889+00:00'::timestamptz),
    ('value-evaluation-v1:2539927ba6241c1d419f154fb7d9ea25cecf6100331bad61c33edcc475fdc157', '2026-09-25T04:45:12.704498+00:00'::timestamptz),
    ('value-evaluation-v1:6bb168dce24f42f007188b2cff552a688c6f4fb9f779517d54e63d1a169b06bb', '2026-09-25T04:45:12.722797+00:00'::timestamptz),
    ('value-evaluation-v1:6711e7b66be5ef4a81fc3f9ca84ab81512462a53e6bfbab0d1c9280d3f0fa4a3', '2026-09-25T04:45:12.742907+00:00'::timestamptz),
    ('value-evaluation-v1:5f2a852979f9311cced1b1061836b5001e7bc4102874b710db76938ad65708a1', '2026-09-25T04:45:12.763051+00:00'::timestamptz),
    ('value-evaluation-v1:c770b976f18a69e199ef0d1f28f678714da27e4948653d974fca028835b50e55', '2026-09-25T04:45:13.662077+00:00'::timestamptz),
    ('value-evaluation-v1:96804cf2f9e95225599bd359e088268174a6052fdb2fcaeb778a38ce9c962cad', '2026-09-25T04:45:13.714478+00:00'::timestamptz),
    ('value-evaluation-v1:1d66cf2bdf819be332300556f021b6eb5cb9cae4c74d3a8762fc2d396e2a4403', '2026-09-25T04:50:28.494909+00:00'::timestamptz),
    ('value-evaluation-v1:ba8e6d1275f8db900c19cf780df2b01634a6632ec4cdcaa819d9ba39f8c0a71e', '2026-09-25T04:59:06.728015+00:00'::timestamptz),
    ('value-evaluation-v1:d16961e847cbcb29e5e49b5bea1682f5d667a147aec2c3485857ec4eeac69edb', '2026-09-25T04:59:06.751255+00:00'::timestamptz),
    ('value-evaluation-v1:e734d4a112ad958dd1a284449e3fb5c4e7a6a5a41215c67fa2f1d4098f34e199', '2026-09-25T05:50:15.720682+00:00'::timestamptz),
    ('value-evaluation-v1:9bc07fc238f9d1939206af7dd4762bfc310b4235da96afb77a321488b210bc97', '2026-09-25T05:56:36.731185+00:00'::timestamptz),
    ('value-evaluation-v1:8fb981ee6809a0f673b628bbdec3bf882c1fb71a5516211af74b7d8fad524fa8', '2026-09-25T05:56:36.753969+00:00'::timestamptz),
    ('value-evaluation-v1:122e887ce40f6d97498514a19c0636b1818c2d6ac888be3f5f6535ab62b378dd', '2026-09-25T05:56:36.776216+00:00'::timestamptz),
    ('value-evaluation-v1:24013bcbd0740f0d0edefbb3bde8b373554b0c5f31d133f97a101a1a090946ca', '2026-09-25T05:56:36.800124+00:00'::timestamptz),
    ('value-evaluation-v1:2e18fab0a6e9417d919029ca8e45bc660e3ddf6dcd306cb67856a1e72042e7fb', '2026-09-25T05:59:46.678306+00:00'::timestamptz),
    ('value-evaluation-v1:204086e154e958f2cb388e37f4507a50bd09170e51ab92ea267ade2483c52603', '2026-09-25T06:05:07.515849+00:00'::timestamptz),
    ('value-evaluation-v1:3c02dd5593404541871822c9a85c9e65e53904aef33570905fc5c818d8383cad', '2026-09-25T06:05:07.536810+00:00'::timestamptz),
    ('value-evaluation-v1:0866100b03952e737e7e84c850d00d495f95c3f902e91294dd510ee81d422640', '2026-09-25T06:06:12.856984+00:00'::timestamptz),
    ('value-evaluation-v1:dca078078d9c3fe98a9cfbd37cd66767209c94dbceea2efd43fbc31e482ec10c', '2026-09-25T06:07:14.537162+00:00'::timestamptz),
    ('value-evaluation-v1:25eaceff640519c4af1bc0422c2d6c03b3fcbe2574beaac9ad7b4f076dcbc172', '2026-09-25T06:07:14.555737+00:00'::timestamptz),
    ('value-evaluation-v1:1512639ec55caa9c0b69d7e5c39433d106c3e13df0b054b45f267cfebbd73388', '2026-09-25T06:07:14.577111+00:00'::timestamptz),
    ('value-evaluation-v1:e0cb5c5f7c4947e18c88469232fe2a6740260b151d585a74e51b77697559bdeb', '2026-09-25T06:07:14.596369+00:00'::timestamptz),
    ('value-evaluation-v1:6e033dc1a78bc43422ada0506075734e63144b23e58d1f1321a56b3347569657', '2026-09-25T06:08:20.521918+00:00'::timestamptz),
    ('value-evaluation-v1:af69f3c5bb402ce9132194fd790213202dd88bd1574800b1f84962b28ebc3d9d', '2026-09-25T06:08:20.543602+00:00'::timestamptz),
    ('value-evaluation-v1:fd53056ace36d8b54cd4a0ad64244d341c4fe3b3aefa32b2c201f478f5ed624d', '2026-09-25T06:08:21.535221+00:00'::timestamptz),
    ('value-evaluation-v1:be3a08b69dca88bb2ac3a9ba4ff5a9e83b98aaa3bc1f7f318dd2c7e5c4e78649', '2026-09-25T06:08:21.563167+00:00'::timestamptz),
    ('value-evaluation-v1:d2ec8ab0c91b7c3791c923f781439c27f5d3a85d18594b6391721c6f7d0c0902', '2026-09-25T06:12:30.636104+00:00'::timestamptz),
    ('value-evaluation-v1:d4205414c94c95d39f43822488fcd81857dbd334eb5272ca9c8de5ec0add48c7', '2026-09-25T06:12:30.660446+00:00'::timestamptz),
    ('value-evaluation-v1:3844b660a55ef95c1fc2a14090afe01672a7c14effd32cf91aea4a2f7514e06f', '2026-09-25T06:12:31.611940+00:00'::timestamptz),
    ('value-evaluation-v1:d8e88ede90ab0bbf8f8b829737f9d73724ea5ac6a203e81c9cb4f38ba540c7cf', '2026-09-25T06:12:31.629374+00:00'::timestamptz),
    ('value-evaluation-v1:98c91b0b833dff2f5115513de8d52a585ef57128d3a2731747dcd3f35a266b15', '2026-09-25T06:18:45.631008+00:00'::timestamptz),
    ('value-evaluation-v1:68e594b048b747909b124beab99ca5f445157b9bcd25dd2132cd20554f7b3b18', '2026-09-25T06:19:49.403681+00:00'::timestamptz),
    ('value-evaluation-v1:4cde9b67e67e406bb94e5c0c98a87a8e6166aaba383b45caedc836248127f92d', '2026-09-25T06:19:49.426044+00:00'::timestamptz),
    ('value-evaluation-v1:8c835122eec4c9217574dfcc81384c9af6aedcdeb55ccb4925418404a8c42dd9', '2026-09-25T06:19:49.445489+00:00'::timestamptz),
    ('value-evaluation-v1:55aa61407faec7766d12af9824d2557bf83c23575004bde9123a9910de95e159', '2026-09-25T06:20:52.825397+00:00'::timestamptz),
    ('value-evaluation-v1:a244729a80a0a82f6870ec3fd5d6bdf9ad7a60a043d20d6741858ffee5e87e27', '2026-09-25T06:20:52.849558+00:00'::timestamptz),
    ('value-evaluation-v1:12803e748c4cba6dcdc982e84bd5a5611d9e4710bea7363e9afa093a3e494e14', '2026-09-25T06:20:52.869596+00:00'::timestamptz),
    ('value-evaluation-v1:157746dcaa212791238b40bedd74d6687d20114b8cddec279d35c196471c6487', '2026-09-25T06:20:52.889968+00:00'::timestamptz),
    ('value-evaluation-v1:71766c4a8f83143e4b82ce1e084398997b787fb2b149a03343ee75761ad9c924', '2026-09-25T07:17:11.467475+00:00'::timestamptz),
    ('value-evaluation-v1:d9c4d5eb0c32112c597d8c68d664acf60ab33fce8a1388f9d3a78406b3a76ce3', '2026-09-25T07:17:11.486427+00:00'::timestamptz),
    ('value-evaluation-v1:54d431e8e2e2b666ba3ec6af160fbed2c1e6dcb61f76bed282b47806b273bc3e', '2026-09-25T07:20:17.334902+00:00'::timestamptz),
    ('value-evaluation-v1:6a3ca4e3b02d472a20b866d4233b9ade52abc2f1b8a6c5e550a9f7177c2dbc53', '2026-09-25T07:20:17.357844+00:00'::timestamptz),
    ('value-evaluation-v1:e8c9ea26b6722d0e3d07ada15cbca9e63842219e6d60dacf7515497e6a5e3638', '2026-09-25T07:26:34.436525+00:00'::timestamptz),
    ('value-evaluation-v1:7b9b0afcc303c0afe84cb059153abdcc2f42398837b907eba8b17d90a44bcd08', '2026-09-25T07:34:01.461358+00:00'::timestamptz),
    ('value-evaluation-v1:6964ea25a1edd755d1194d213ddab49884f376f066353edc866b49f67d84013d', '2026-09-25T07:34:01.485204+00:00'::timestamptz),
    ('value-evaluation-v1:867ecf2de24e827015fc39e00b98a218a37e24b951bc206f1da57a0b22767d4e', '2026-09-25T07:47:23.520201+00:00'::timestamptz),
    ('value-evaluation-v1:033b9b7ab36e3348e9f882915c414118af201b61b0790a85607676d4c1038e4a', '2026-09-25T07:47:23.543534+00:00'::timestamptz),
    ('value-evaluation-v1:1182247191c7a3e88feb926676220eaa3c84d1b48cc7d6be9cba0f96ef7cf8a9', '2026-09-25T08:07:32.520370+00:00'::timestamptz),
    ('value-evaluation-v1:8407d38a7cfd0baec178994190dc867a9ed62262926a30291907c9dbf18d48d5', '2026-09-25T08:16:44.929990+00:00'::timestamptz),
    ('value-evaluation-v1:7c9f02c48dc0d86cf640b7d447b6f0dd31903965e08d3169bd03bffa1fe4f521', '2026-09-25T08:18:50.094553+00:00'::timestamptz),
    ('value-evaluation-v1:b6fd1544c4cd2a9e422e9caff27a3799e451c5ae15915aaded063e6a877f54b9', '2026-09-25T08:18:50.117570+00:00'::timestamptz),
    ('value-evaluation-v1:747344ee1c3c08432202541fa369a17288c00443a7a6ac24b7697ddff2d6380c', '2026-09-25T08:42:53.983511+00:00'::timestamptz),
    ('value-evaluation-v1:d4d2e34f6f46fe23b6b025a593700236dc13dcfe19dcf719dfe939a54aad848d', '2026-09-25T08:42:54.006472+00:00'::timestamptz),
    ('value-evaluation-v1:7ea26841474b49d4c75b6f46cdb0c78fa522b438a809d6a368770e672a18f0ee', '2026-09-25T08:42:54.035569+00:00'::timestamptz),
    ('value-evaluation-v1:8e7d8bd1b486aa8efdd11dcf6b17d7f46f2188e9c38b5a30672f31065f134d70', '2026-09-25T08:42:54.063393+00:00'::timestamptz),
    ('value-evaluation-v1:72b20e82aa4d5cb4303682e2e34c1929cffb2c0b1d3c234fb381d0c87039f1c9', '2026-09-25T08:51:07.181306+00:00'::timestamptz),
    ('value-evaluation-v1:d019c8e9a5bed1b72a74730e6aeaf7ea8b7d591f5444bb14e413938576a5f420', '2026-09-25T08:51:07.201723+00:00'::timestamptz),
    ('value-evaluation-v1:ee4f87222cd739c8a739267695979de3ec658233fa147a5ae2a4b65cf298675a', '2026-09-25T09:18:25.194454+00:00'::timestamptz),
    ('value-evaluation-v1:81f3a65d13e55017def1f490d57a1587f8faafef9052dfc001adcea322c0a955', '2026-09-25T09:21:32.680792+00:00'::timestamptz),
    ('value-evaluation-v1:27a7576d375b846b5ce4697d1a955bcd2e0afa0489a7cd76baaa01ef7b7595ff', '2026-09-25T09:40:33.519017+00:00'::timestamptz),
    ('value-evaluation-v1:9efe0667a13fffd43fcb1b8e6036bc570ef9f0a978666500492419cfa73898d5', '2026-09-25T09:41:34.708287+00:00'::timestamptz),
    ('value-evaluation-v1:6a7191397e9e69b77e978dfc9e9d5c54130f4ee624a76c1ea3421f763f1518ea', '2026-09-25T09:41:35.593747+00:00'::timestamptz),
    ('value-evaluation-v1:9ce3f2ebb22600948379a1c4a8673c681d920aa95114d2d7ecd615ca082edfa2', '2026-09-25T09:41:35.613969+00:00'::timestamptz),
    ('value-evaluation-v1:23d8e543f0d794ade3b6575facddadbf228cc229087cdf68b96915562d3072ab', '2026-09-25T09:41:35.632760+00:00'::timestamptz),
    ('value-evaluation-v1:c27e64611482d1a15751e5103095dbe8ab35b54ba6184f9deb29f1f0a360ce79', '2026-09-25T09:42:36.789251+00:00'::timestamptz),
    ('value-evaluation-v1:2105fa54ea74e7e1673a55e4b2a657c9bd060a2011c63f667e5ccbdf282bde37', '2026-09-25T09:42:37.608265+00:00'::timestamptz),
    ('value-evaluation-v1:fa43d4cc00e9e5b6b0f33b190d8abc3078b87f2ee9b7da44212d1f90cdbe3dec', '2026-09-25T09:42:37.626861+00:00'::timestamptz),
    ('value-evaluation-v1:521c83f48f79c38e69df6346b48b3fbe11fd76143ab7411f9e5eed6cb14edb30', '2026-09-25T09:42:37.645468+00:00'::timestamptz),
    ('value-evaluation-v1:9bc45ff8e7c3dbe77d9da48e0bcad0de2d5e4475d75af4cea267f6b33c9eb83c', '2026-09-25T09:43:39.700415+00:00'::timestamptz),
    ('value-evaluation-v1:911b6f70110b79ec33d3a7deeedd278fc3d376fe611cebad7da41726121f8ade', '2026-09-25T09:43:39.724477+00:00'::timestamptz),
    ('value-evaluation-v1:e1d5ca0dde6d85c816eaff75ae4cbcf5a54d0ea1d0b8588e45f7368ae934585a', '2026-09-25T09:43:39.744846+00:00'::timestamptz),
    ('value-evaluation-v1:7f10e228230175a348ccec292eadcfec19d725b47a68c76e5553a28929554da0', '2026-09-25T09:43:39.767530+00:00'::timestamptz),
    ('value-evaluation-v1:eae1f22057d27331fffe5d7508d517b1764c4b08096963e2df2f66538dc4b068', '2026-09-25T09:44:42.703789+00:00'::timestamptz),
    ('value-evaluation-v1:80affb6e3abdf91da12768c6ffc0cbbe8af42a8dd3bc8a0f84b51094747c516b', '2026-09-25T09:44:42.724679+00:00'::timestamptz),
    ('value-evaluation-v1:d617ec6d3c8fad9e4c782b2fe42abd84375adc7a86a964e792139ce4fea296a8', '2026-09-25T09:47:48.821439+00:00'::timestamptz),
    ('value-evaluation-v1:89320fb80898cdfb16a8baaf3f9984e8b8498aa646e2eee7f9025c1395ed113f', '2026-09-25T09:47:48.841433+00:00'::timestamptz),
    ('value-evaluation-v1:7fa8d7b516e891722483e084823e4c09bcd207aff9e81b8223d880937c751639', '2026-09-25T09:47:49.629395+00:00'::timestamptz),
    ('value-evaluation-v1:4008c282e4895a3d093df9bcaef50265849127f819a6a667bbae8adda109125c', '2026-09-25T09:47:49.649193+00:00'::timestamptz),
    ('value-evaluation-v1:04723c411bbf382a640578e1dd38e628cfdaad42d41cd059c4f25b6aef1b3e70', '2026-09-25T09:47:49.670853+00:00'::timestamptz),
    ('value-evaluation-v1:38fc0b43c0c16511880fb02c063d015ca4fd46be747bca5c2e1c3f850129cf34', '2026-09-25T09:48:50.954132+00:00'::timestamptz),
    ('value-evaluation-v1:da3a32c2751e98994320e7c6dbd0c9ce19d606a5c652250076e8f1f31425b2bc', '2026-09-25T09:48:50.975231+00:00'::timestamptz),
    ('value-evaluation-v1:2e58bc41a1bab795220b6ea25391c3561de89c044d75e3299c86029e608f1b8b', '2026-09-25T09:48:51.008551+00:00'::timestamptz),
    ('value-evaluation-v1:3f406e001f97fa8d9f4faf40755de5adea08ad5624118d7b8f3a3c1ab76e2082', '2026-09-25T09:48:51.029238+00:00'::timestamptz),
    ('value-evaluation-v1:cfb8b1ba2582456a04aaf141abce5b563825c3a960ed609bca13c7f28e6b120c', '2026-09-25T09:48:51.887555+00:00'::timestamptz),
    ('value-evaluation-v1:d4ec041e655b2c1bc5da9d988e0bb211eb51e5537a7de8e5e1aa586dd65ff10d', '2026-09-25T09:48:51.914010+00:00'::timestamptz),
    ('value-evaluation-v1:863ac9fa1c2d48e2fe8ba6110961b63556a31764591d0359c0e4b842eccb866a', '2026-09-25T09:48:51.935124+00:00'::timestamptz),
    ('value-evaluation-v1:fd7fe8df571ef1cd098ee5888a199a693e3a0ffc6d2e2bff865f26fd63916429', '2026-09-25T09:48:51.956783+00:00'::timestamptz),
    ('value-evaluation-v1:eb954754c0830083372a48bb9762ae0ea6c05907f7a24c3d982cc9f2731992ed', '2026-09-25T09:53:04.448018+00:00'::timestamptz),
    ('value-evaluation-v1:3b3f9e2755ea4b2c1a6881d61ef5935dabe9f49389db1cc5aa33043fc7e3cdab', '2026-09-25T09:53:04.468025+00:00'::timestamptz),
    ('value-evaluation-v1:e0c1bf91da635e387b99ad997fccf1e33722e569ea405dfd76a6015c7e9e58bd', '2026-09-25T09:53:04.488435+00:00'::timestamptz),
    ('value-evaluation-v1:01715c35901bd76647ea4ebf269b5b6efa8cd64c5d85627b825c6a6540389ad7', '2026-09-25T09:53:04.507773+00:00'::timestamptz),
    ('value-evaluation-v1:e6c5ec5539f957241d0af917199317e499b7ea7a3db888da02ebe52dbecd68a5', '2026-09-25T09:54:07.237351+00:00'::timestamptz),
    ('value-evaluation-v1:cbda3dc76026f7152a76d9bef284befd167ebd414d318ad59fa7122942b8f29e', '2026-09-25T09:54:07.256727+00:00'::timestamptz),
    ('value-evaluation-v1:b9fadb5689d159cbe697fe7503280165633441759ea53464f3f61193fdd2bd17', '2026-09-25T09:54:07.277169+00:00'::timestamptz),
    ('value-evaluation-v1:d262ca057bc8537808853c375b612ae2c33936bed84628f170b7c18355d9ef5a', '2026-09-25T09:55:12.019021+00:00'::timestamptz),
    ('value-evaluation-v1:86eb9e12b446f428bd5d0216212b381638bba66bd1db46d4be32056be3cb2d44', '2026-09-25T09:55:12.040269+00:00'::timestamptz),
    ('value-evaluation-v1:4614ce6232d74483e5791db1cf4ddb6fa6e5c2e1735ecbe225f0ff63c00da5e4', '2026-09-25T09:55:12.063229+00:00'::timestamptz),
    ('value-evaluation-v1:25fb86df11153679b4fd79c3568c39a039a374d8862b17779396d62f748208bb', '2026-09-25T09:55:12.085616+00:00'::timestamptz),
    ('value-evaluation-v1:7d733b542096506d38d3bbadb82ff2fbca946cf58ae53cc083f63264598549a2', '2026-09-25T09:58:26.253571+00:00'::timestamptz),
    ('value-evaluation-v1:6ac383411e47e8aa5ca1835e0a750322fe3efe35f8b200abc3eda090eb618052', '2026-09-25T09:59:29.943484+00:00'::timestamptz),
    ('value-evaluation-v1:9ed2a45d71094d35d54c6316f8ea844e3bce8c65ca67f161818b33e0f91583c2', '2026-09-25T09:59:29.964134+00:00'::timestamptz),
    ('value-evaluation-v1:b3b7a2bc532431f50a2b7ed23e4aea3881d14a5c6383d6cc7c85a24814c9d375', '2026-09-25T10:24:28.343938+00:00'::timestamptz),
    ('value-evaluation-v1:7e8ca0eaf60b43c0cf5d5231592780e0e33486872157bfb6a9fa3f0b07790a99', '2026-09-25T10:24:28.364417+00:00'::timestamptz),
    ('value-evaluation-v1:ac266174a59d126ad8419fbc2e4fb5196620c6d4072cb2b04cdad4adfb85920e', '2026-09-25T10:43:30.450355+00:00'::timestamptz),
    ('value-evaluation-v1:17ed2b1871471c6e894402a48cce255d3743fe1269becea1a41969553e38439a', '2026-09-25T10:48:39.793659+00:00'::timestamptz),
    ('value-evaluation-v1:bb9f4d293461f906b0daca5402892c921d486a19c5cc1f4674c5ed75abf2c7ec', '2026-09-25T10:48:39.813889+00:00'::timestamptz),
    ('value-evaluation-v1:1358e48433ac4242bc60c341500be46ff6ca607ab4c14e71f0d5dc073ff8387f', '2026-09-25T11:24:02.759588+00:00'::timestamptz),
    ('value-evaluation-v1:998ea634fc2b1f6bf9d0905493aff9fd9637aa577ca946afaf5d082b96777f6b', '2026-09-25T11:24:02.780854+00:00'::timestamptz),
    ('value-evaluation-v1:e548c24f4348e5656ac793608f036bcab6b4baa000101c0435b8586a8119972a', '2026-09-25T11:24:02.801471+00:00'::timestamptz),
    ('value-evaluation-v1:427b8ac13bfb86b7e58a5dc0d821522f68cdf0179f4a40719b7f551bedba99d1', '2026-09-25T11:24:02.824219+00:00'::timestamptz),
    ('value-evaluation-v1:ecfdd77d84564ce766f44586f404658464016ddddad1fdf7ca967a25b2d9bfba', '2026-09-25T11:26:10.153117+00:00'::timestamptz),
    ('value-evaluation-v1:f1e17a55a4d970ec87d3a84207677e4e2381fd99dcfba5dd96ed4976d412f23f', '2026-09-25T11:26:10.180207+00:00'::timestamptz),
    ('value-evaluation-v1:0961734f67f038f089c10dd7ccec7071953b5105602e0fa0fcce9465145cd220', '2026-09-25T11:26:10.205279+00:00'::timestamptz),
    ('value-evaluation-v1:b4c2b02a68534aaa03cbd38c5ec68715ae4020f49cd2a32651233f905d4ecae0', '2026-09-25T11:26:10.228261+00:00'::timestamptz),
    ('value-evaluation-v1:13fc12c0a6150aa793dcf10ba0c45848883f556beb1f906ae3e434d7953751c8', '2026-09-25T11:37:54.297150+00:00'::timestamptz),
    ('value-evaluation-v1:ef43063ba64e22ae0d7cff9f80cef22e131c90c0656279eb668369bb7e2f0737', '2026-09-25T11:37:54.348407+00:00'::timestamptz),
    ('value-evaluation-v1:fd5c44025958fec7618cf91ef90a3f8c75b545d2f87e52facb3a8aed08ccbeb0', '2026-09-25T11:38:57.965537+00:00'::timestamptz),
    ('value-evaluation-v1:0b333b092d50004de1291d996467ef2b1ad38cb231b9a334ff37f4254f4bdddf', '2026-09-25T11:38:57.986479+00:00'::timestamptz)
)
INSERT INTO research_signals (
    signal_id, evaluation_id, fixture_id, blocked_at, blocked_stage,
    reason_codes, capture_method, policy_fingerprint, policy_configuration
)
SELECT
    regexp_replace(seed.evaluation_id, '^value-evaluation-v1:', 'research-signal-v1:'),
    seed.evaluation_id,
    e.fixture_id,
    seed.blocked_at,
    'PRELIMINARY_RISK',
    ARRAY['MAX_OPEN_EXPOSURE_EXCEEDED']::TEXT[],
    'LOG_BACKFILL_V1',
    NULL,
    NULL
FROM seed
JOIN value_evaluations e ON e.evaluation_id = seed.evaluation_id
ON CONFLICT DO NOTHING;