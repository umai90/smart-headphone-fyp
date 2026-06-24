import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/translation_provider.dart';
import '../services/deepfake_service.dart';
import '../services/pi_service.dart';
import '../utils/app_theme.dart';

class DeepfakeScreen extends StatefulWidget {
  const DeepfakeScreen({super.key});

  @override
  State<DeepfakeScreen> createState() => _DeepfakeScreenState();
}

class _DeepfakeScreenState extends State<DeepfakeScreen> {
  final _service = DeepfakeService();

  List<RecordingFile> _recordings = [];
  bool _loading = false;
  bool _serverOk = false;
  String? _error;

  // filename -> result
  final Map<String, DeepfakeResult> _results = {};
  // filenames currently being analyzed
  final Set<String> _analyzing = {};
  bool _analyzingAll = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  String get _serverUrl =>
      context.read<TranslationProvider>().serverUrl;

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });

    final ok = await _service.checkHealth(_serverUrl);
    if (!mounted) return;

    if (!ok) {
      setState(() {
        _loading = false;
        _serverOk = false;
        _error =
            'Server not reachable.\nStart Python server and check IP in Settings.';
      });
      return;
    }

    final recs =
        await PiService(_serverUrl).getRecordings(source: 'pi');
    if (!mounted) return;

    setState(() {
      _serverOk = true;
      _recordings = recs;
      _loading = false;
    });
  }

  Future<void> _testOne(RecordingFile rec) async {
    if (_analyzing.contains(rec.name)) return;
    setState(() => _analyzing.add(rec.name));

    final result = await _service.detectRecording(rec.name, _serverUrl);
    if (!mounted) return;

    setState(() {
      if (result != null) _results[rec.name] = result;
      _analyzing.remove(rec.name);
    });
  }

  Future<void> _testAll() async {
    if (_analyzingAll || _recordings.isEmpty) return;
    setState(() {
      _analyzingAll = true;
      _results.clear();
    });

    for (final rec in _recordings) {
      if (!mounted) return;
      setState(() => _analyzing.add(rec.name));
      final result = await _service.detectRecording(rec.name, _serverUrl);
      if (!mounted) return;
      setState(() {
        if (result != null) _results[rec.name] = result;
        _analyzing.remove(rec.name);
      });
    }

    if (mounted) setState(() => _analyzingAll = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [Color(0xFF060D1F), Color(0xFF0E1E3C), Color(0xFF162D4A)],
          ),
        ),
        child: SafeArea(
          child: Column(
            children: [
              _buildHeader(),
              _buildServerBanner(),
              Expanded(child: _buildBody()),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() => Padding(
        padding: const EdgeInsets.fromLTRB(20, 14, 20, 10),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(9),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                    colors: [Color(0xFF1A3A5C), Color(0xFF0D2137)]),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                    color: AppTheme.accent.withValues(alpha: 0.35)),
              ),
              child: const Icon(Icons.security_rounded,
                  color: AppTheme.accent, size: 22),
            ),
            const SizedBox(width: 14),
            const Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Deepfake Detection',
                      style: TextStyle(
                          color: Colors.white,
                          fontSize: 17,
                          fontWeight: FontWeight.bold)),
                  Text('TEST RECORDED VOICES',
                      style: TextStyle(
                          color: AppTheme.accent,
                          fontSize: 9,
                          letterSpacing: 2.2,
                          fontWeight: FontWeight.w600)),
                ],
              ),
            ),
            // Refresh button
            GestureDetector(
              onTap: _load,
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: AppTheme.accent.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.refresh_rounded,
                    color: AppTheme.accent, size: 20),
              ),
            ),
          ],
        ),
      );

  Widget _buildServerBanner() {
    final url = context.select<TranslationProvider, String>((p) => p.serverUrl);
    final color = _serverOk ? AppTheme.accentGreen : Colors.redAccent;
    return Container(
      margin: const EdgeInsets.fromLTRB(20, 0, 20, 10),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Container(
            width: 7,
            height: 7,
            decoration: BoxDecoration(shape: BoxShape.circle, color: color),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _serverOk ? 'Server connected — $url' : 'Server offline — $url',
              style: TextStyle(color: color, fontSize: 11),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBody() {
    if (_loading) {
      return const Center(
          child: CircularProgressIndicator(color: AppTheme.accent));
    }

    if (_error != null) {
      return _ErrorView(message: _error!, onRetry: _load);
    }

    if (_recordings.isEmpty) {
      return _EmptyView(onRetry: _load);
    }

    return Column(
      children: [
        // Summary + Test All button
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 0, 20, 10),
          child: Row(
            children: [
              Text(
                '${_recordings.length} recording(s) found',
                style: const TextStyle(color: Colors.white54, fontSize: 13),
              ),
              const Spacer(),
              _analyzingAll
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: AppTheme.accentGreen),
                    )
                  : ElevatedButton.icon(
                      onPressed: _testAll,
                      icon: const Icon(Icons.playlist_play_rounded, size: 16),
                      label: const Text('Test All'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor:
                            AppTheme.accentGreen.withValues(alpha: 0.15),
                        foregroundColor: AppTheme.accentGreen,
                        elevation: 0,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 14, vertical: 8),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(10),
                          side: BorderSide(
                              color: AppTheme.accentGreen
                                  .withValues(alpha: 0.4)),
                        ),
                      ),
                    ),
            ],
          ),
        ),
        // Recordings list
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
            itemCount: _recordings.length,
            itemBuilder: (_, i) {
              final rec = _recordings[i];
              return _RecordingTile(
                rec: rec,
                result: _results[rec.name],
                isAnalyzing: _analyzing.contains(rec.name),
                onTest: () => _testOne(rec),
              );
            },
          ),
        ),
      ],
    );
  }
}

// ── Recording Tile ────────────────────────────────────────────────────────────

class _RecordingTile extends StatelessWidget {
  final RecordingFile rec;
  final DeepfakeResult? result;
  final bool isAnalyzing;
  final VoidCallback onTest;

  const _RecordingTile({
    required this.rec,
    required this.result,
    required this.isAnalyzing,
    required this.onTest,
  });

  @override
  Widget build(BuildContext context) {
    final hasResult = result != null;
    final isReal = hasResult && result!.isReal;
    final resultColor =
        hasResult ? (isReal ? AppTheme.accentGreen : Colors.redAccent) : null;

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: hasResult
              ? [
                  resultColor!.withValues(alpha: 0.07),
                  resultColor.withValues(alpha: 0.02),
                ]
              : [const Color(0xFF0E1E38), const Color(0xFF152A44)],
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: hasResult
              ? resultColor!.withValues(alpha: 0.35)
              : Colors.white.withValues(alpha: 0.08),
        ),
      ),
      child: Column(
        children: [
          // File info + Test button
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppTheme.accent.withValues(alpha: 0.1),
                    shape: BoxShape.circle,
                  ),
                  child: const Icon(Icons.audio_file_rounded,
                      color: AppTheme.accent, size: 18),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        rec.name,
                        style: const TextStyle(
                            color: Colors.white,
                            fontSize: 13,
                            fontWeight: FontWeight.w500),
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 3),
                      Text(
                        '${rec.sizeMb.toStringAsFixed(2)} MB  •  ${rec.date}',
                        style: const TextStyle(
                            color: Colors.white38, fontSize: 11),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 10),
                isAnalyzing
                    ? const SizedBox(
                        width: 28,
                        height: 28,
                        child: CircularProgressIndicator(
                            strokeWidth: 2, color: AppTheme.accent),
                      )
                    : GestureDetector(
                        onTap: onTest,
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 14, vertical: 7),
                          decoration: BoxDecoration(
                            color: AppTheme.accent.withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                                color: AppTheme.accent
                                    .withValues(alpha: 0.35)),
                          ),
                          child: Text(
                            hasResult ? 'Re-test' : 'Test',
                            style: const TextStyle(
                                color: AppTheme.accent,
                                fontSize: 12,
                                fontWeight: FontWeight.w600),
                          ),
                        ),
                      ),
              ],
            ),
          ),

          // Result section — same info as Python output
          if (hasResult) ...[
            Divider(
                height: 1,
                color: resultColor!.withValues(alpha: 0.25)),
            Padding(
              padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // REAL / FAKE label
                  Row(
                    children: [
                      Icon(
                        isReal
                            ? Icons.check_circle_rounded
                            : Icons.cancel_rounded,
                        color: resultColor,
                        size: 20,
                      ),
                      const SizedBox(width: 8),
                      Text(
                        isReal ? 'REAL VOICE' : 'FAKE VOICE',
                        style: TextStyle(
                            color: resultColor,
                            fontSize: 15,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 1.2),
                      ),
                      const Spacer(),
                      Container(
                        padding: const EdgeInsets.symmetric(
                            horizontal: 10, vertical: 4),
                        decoration: BoxDecoration(
                          color: resultColor.withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(
                              color:
                                  resultColor.withValues(alpha: 0.35)),
                        ),
                        child: Text(
                          '${result!.confidence.toStringAsFixed(1)}% confident',
                          style: TextStyle(
                              color: resultColor,
                              fontSize: 11,
                              fontWeight: FontWeight.bold),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  // Real prob bar
                  _ProbRow(
                    label: 'Real probability',
                    value: result!.realProb,
                    color: AppTheme.accentGreen,
                  ),
                  const SizedBox(height: 6),
                  // Fake prob bar
                  _ProbRow(
                    label: 'Fake probability',
                    value: result!.fakeProb,
                    color: Colors.redAccent,
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _ProbRow extends StatelessWidget {
  final String label;
  final double value;
  final Color color;

  const _ProbRow(
      {required this.label, required this.value, required this.color});

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label,
                  style:
                      const TextStyle(color: Colors.white54, fontSize: 11)),
              Text('${value.toStringAsFixed(1)}%',
                  style: TextStyle(
                      color: color,
                      fontSize: 11,
                      fontWeight: FontWeight.bold)),
            ],
          ),
          const SizedBox(height: 4),
          ClipRRect(
            borderRadius: BorderRadius.circular(4),
            child: LinearProgressIndicator(
              value: value / 100,
              backgroundColor: color.withValues(alpha: 0.1),
              valueColor: AlwaysStoppedAnimation<Color>(color),
              minHeight: 5,
            ),
          ),
        ],
      );
}

// ── Empty View ────────────────────────────────────────────────────────────────

class _EmptyView extends StatelessWidget {
  final VoidCallback onRetry;
  const _EmptyView({required this.onRetry});

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                padding: const EdgeInsets.all(26),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white.withValues(alpha: 0.03),
                  border:
                      Border.all(color: Colors.white.withValues(alpha: 0.07)),
                ),
                child: const Icon(Icons.mic_off_rounded,
                    color: Colors.white10, size: 52),
              ),
              const SizedBox(height: 20),
              const Text('No recordings found',
                  style: TextStyle(color: Colors.white38, fontSize: 15)),
              const SizedBox(height: 8),
              const Text(
                'Record a conversation first from the\nTranslate screen, then test here.',
                textAlign: TextAlign.center,
                style: TextStyle(
                    color: Colors.white24, fontSize: 12, height: 1.5),
              ),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded, size: 16),
                label: const Text('Refresh'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.accent,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ],
          ),
        ),
      );
}

// ── Error View ────────────────────────────────────────────────────────────────

class _ErrorView extends StatelessWidget {
  final String message;
  final VoidCallback onRetry;
  const _ErrorView({required this.message, required this.onRetry});

  @override
  Widget build(BuildContext context) => Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_rounded,
                  color: Colors.white24, size: 52),
              const SizedBox(height: 16),
              Text(message,
                  textAlign: TextAlign.center,
                  style:
                      const TextStyle(color: Colors.white38, fontSize: 13, height: 1.5)),
              const SizedBox(height: 24),
              ElevatedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh_rounded, size: 16),
                label: const Text('Retry'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: AppTheme.accent,
                  foregroundColor: Colors.white,
                  shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ],
          ),
        ),
      );
}
