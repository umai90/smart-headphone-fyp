import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/translation_provider.dart';
import '../services/pi_service.dart';
import '../utils/app_theme.dart';

class RecordingsScreen extends StatefulWidget {
  const RecordingsScreen({super.key});

  @override
  State<RecordingsScreen> createState() => _RecordingsScreenState();
}

class _RecordingsScreenState extends State<RecordingsScreen> {
  List<RecordingFile> _recordings = [];
  bool _loading = false;
  bool _backing = false;
  String? _error;
  String _source = 'all'; // 'all' | 'pi' | 'cloud'

  String? _playingName;
  final AudioPlayer _player = AudioPlayer();

  @override
  void initState() {
    super.initState();
    _player.onPlayerComplete.listen((_) {
      if (mounted) setState(() => _playingName = null);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _player.dispose();
    super.dispose();
  }

  PiService get _svc {
    final url = context.read<TranslationProvider>().serverUrl;
    return PiService(url);
  }

  Future<void> _load() async {
    if (!mounted) return;
    setState(() {
      _loading = true;
      _error = null;
    });
    // Check server first so we can show a meaningful error
    final alive = await _svc.checkHealth();
    if (!mounted) return;
    if (!alive) {
      setState(() {
        _loading = false;
        _error = 'Cannot reach Pi server.\nCheck IP in Settings and make sure Flask is running.';
      });
      return;
    }
    final result = await _svc.getRecordings(source: _source);
    if (!mounted) return;
    setState(() {
      _recordings = result;
      _loading = false;
    });
  }

  Future<void> _play(RecordingFile rec) async {
    if (_playingName == rec.name) {
      await _player.stop();
      setState(() => _playingName = null);
      return;
    }
    await _player.stop();
    setState(() => _playingName = rec.name);
    final url = _svc.getRecordingStreamUrl(rec.name);
    await _player.play(UrlSource(url));
  }

  Future<void> _delete(RecordingFile rec) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: const Color(0xFF0E1E3C),
        title: const Text('Delete Recording',
            style: TextStyle(color: Colors.white)),
        content: Text('Delete "${rec.name}"?',
            style: const TextStyle(color: Colors.white70)),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancel',
                  style: TextStyle(color: Colors.white38))),
          TextButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Delete',
                  style: TextStyle(color: Colors.redAccent))),
        ],
      ),
    );
    if (confirm != true || !mounted) return;
    final ok = await _svc.deleteRecording(rec.name);
    if (!mounted) return;
    if (ok) {
      _showSnack('Deleted ${rec.name}', AppTheme.accentGreen);
      _load();
    } else {
      _showSnack('Delete failed', Colors.redAccent);
    }
  }

  Future<void> _backup() async {
    setState(() => _backing = true);
    final ok = await _svc.triggerBackup();
    if (!mounted) return;
    setState(() => _backing = false);
    _showSnack(
      ok ? 'Backup started — uploading to Google Drive' : 'Backup failed',
      ok ? AppTheme.accentGreen : Colors.redAccent,
    );
    if (ok) Future.delayed(const Duration(seconds: 3), _load);
  }

  void _showSnack(String msg, Color color) {
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(msg, style: const TextStyle(color: Colors.white)),
      backgroundColor: color.withValues(alpha: 0.85),
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      margin: const EdgeInsets.all(16),
      duration: const Duration(seconds: 3),
    ));
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
              _Header(onRefresh: _load, onBackup: _backing ? null : _backup,
                  backing: _backing),
              _FilterBar(
                selected: _source,
                onSelect: (s) {
                  setState(() => _source = s);
                  _load();
                },
              ),
              Expanded(child: _body()),
            ],
          ),
        ),
      ),
    );
  }

  Widget _body() {
    if (_loading) {
      return const Center(
          child: CircularProgressIndicator(color: AppTheme.accent));
    }
    if (_error != null) {
      return _ErrorView(message: _error!, onRetry: _load);
    }
    if (_recordings.isEmpty) {
      return _EmptyView(source: _source);
    }
    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 24),
      itemCount: _recordings.length,
      itemBuilder: (_, i) => _RecordingTile(
        rec: _recordings[i],
        isPlaying: _playingName == _recordings[i].name,
        onPlay: _recordings[i].isCloud ? null : () => _play(_recordings[i]),
        onDelete: _recordings[i].isCloud ? null : () => _delete(_recordings[i]),
      ),
    );
  }
}

// ─── Header ──────────────────────────────────────────────────────────────────

class _Header extends StatelessWidget {
  final VoidCallback onRefresh;
  final VoidCallback? onBackup;
  final bool backing;

  const _Header(
      {required this.onRefresh,
      required this.onBackup,
      required this.backing});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 16, 10),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(9),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                  colors: [Color(0xFF1A3A5C), Color(0xFF0D2137)]),
              borderRadius: BorderRadius.circular(14),
              border:
                  Border.all(color: AppTheme.accent.withValues(alpha: 0.35)),
            ),
            child: const Icon(Icons.folder_special_rounded,
                color: AppTheme.accent, size: 22),
          ),
          const SizedBox(width: 14),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Recordings',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 17,
                        fontWeight: FontWeight.bold)),
                Text('Pi Storage & Cloud Backup',
                    style: TextStyle(
                        color: AppTheme.accent,
                        fontSize: 9,
                        letterSpacing: 1.8,
                        fontWeight: FontWeight.w600)),
              ],
            ),
          ),
          if (backing)
            const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(
                  strokeWidth: 2, color: AppTheme.accentGreen),
            )
          else
            _IconBtn(
              icon: Icons.cloud_upload_rounded,
              color: AppTheme.accentGreen,
              tooltip: 'Backup to Google Drive',
              onTap: onBackup ?? () {},
            ),
          const SizedBox(width: 4),
          _IconBtn(
            icon: Icons.refresh_rounded,
            color: AppTheme.accent,
            tooltip: 'Refresh',
            onTap: onRefresh,
          ),
        ],
      ),
    );
  }
}

class _IconBtn extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String tooltip;
  final VoidCallback onTap;

  const _IconBtn(
      {required this.icon,
      required this.color,
      required this.tooltip,
      required this.onTap});

  @override
  Widget build(BuildContext context) => Tooltip(
        message: tooltip,
        child: GestureDetector(
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, color: color, size: 20),
          ),
        ),
      );
}

// ─── Filter Bar ───────────────────────────────────────────────────────────────

class _FilterBar extends StatelessWidget {
  final String selected;
  final void Function(String) onSelect;

  const _FilterBar({required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
      child: Row(
        children: [
          _FilterChip(label: 'All', value: 'all', selected: selected, onSelect: onSelect),
          const SizedBox(width: 8),
          _FilterChip(label: 'Pi Storage', value: 'pi', selected: selected, onSelect: onSelect),
          const SizedBox(width: 8),
          _FilterChip(label: 'Cloud', value: 'cloud', selected: selected, onSelect: onSelect),
        ],
      ),
    );
  }
}

class _FilterChip extends StatelessWidget {
  final String label;
  final String value;
  final String selected;
  final void Function(String) onSelect;

  const _FilterChip(
      {required this.label,
      required this.value,
      required this.selected,
      required this.onSelect});

  @override
  Widget build(BuildContext context) {
    final active = selected == value;
    return GestureDetector(
      onTap: () => onSelect(value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        decoration: BoxDecoration(
          color: active
              ? AppTheme.accent.withValues(alpha: 0.15)
              : Colors.white.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
            color: active
                ? AppTheme.accent.withValues(alpha: 0.5)
                : Colors.white12,
          ),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: active ? AppTheme.accent : Colors.white38,
            fontSize: 12,
            fontWeight: active ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}

// ─── Recording Tile ───────────────────────────────────────────────────────────

class _RecordingTile extends StatelessWidget {
  final RecordingFile rec;
  final bool isPlaying;
  final VoidCallback? onPlay;
  final VoidCallback? onDelete;

  const _RecordingTile({
    required this.rec,
    required this.isPlaying,
    required this.onPlay,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    final isCloud = rec.isCloud;
    final accentColor = isCloud ? AppTheme.accentGreen : AppTheme.accent;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          colors: isCloud
              ? [const Color(0xFF0E2A1C), const Color(0xFF14362A)]
              : [const Color(0xFF0E1E38), const Color(0xFF152A44)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: accentColor.withValues(alpha: 0.2)),
      ),
      child: Row(
        children: [
          GestureDetector(
            onTap: onPlay,
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              width: 44,
              height: 44,
              decoration: BoxDecoration(
                color: onPlay == null
                    ? Colors.white.withValues(alpha: 0.04)
                    : isPlaying
                        ? accentColor.withValues(alpha: 0.25)
                        : accentColor.withValues(alpha: 0.1),
                shape: BoxShape.circle,
                border: Border.all(
                  color: onPlay == null
                      ? Colors.white12
                      : accentColor.withValues(alpha: 0.4),
                ),
              ),
              child: Icon(
                isPlaying
                    ? Icons.stop_rounded
                    : onPlay == null
                        ? Icons.cloud_done_rounded
                        : Icons.play_arrow_rounded,
                color: onPlay == null ? Colors.white24 : accentColor,
                size: 22,
              ),
            ),
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
                const SizedBox(height: 4),
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: accentColor.withValues(alpha: 0.12),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        isCloud ? 'Cloud' : 'Pi',
                        style: TextStyle(
                            color: accentColor,
                            fontSize: 10,
                            fontWeight: FontWeight.bold),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '${rec.sizeMb.toStringAsFixed(2)} MB',
                      style: const TextStyle(
                          color: Colors.white38, fontSize: 11),
                    ),
                    if (rec.date.isNotEmpty) ...[
                      const SizedBox(width: 8),
                      Flexible(
                        child: Text(
                          rec.date,
                          style: const TextStyle(
                              color: Colors.white24, fontSize: 11),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ],
                ),
              ],
            ),
          ),
          if (onDelete != null)
            GestureDetector(
              onTap: onDelete,
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  color: Colors.red.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: const Icon(Icons.delete_outline_rounded,
                    color: Colors.redAccent, size: 18),
              ),
            ),
        ],
      ),
    );
  }
}

// ─── Empty / Error Views ──────────────────────────────────────────────────────

class _EmptyView extends StatelessWidget {
  final String source;
  const _EmptyView({required this.source});

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
              Text(
                source == 'cloud'
                    ? 'Cloud backups appear here after upload'
                    : 'Recordings are saved on the Raspberry Pi\nafter translation sessions',
                textAlign: TextAlign.center,
                style:
                    const TextStyle(color: Colors.white24, fontSize: 12, height: 1.5),
              ),
            ],
          ),
        ),
      );
}

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
                  style: const TextStyle(color: Colors.white38, fontSize: 13)),
              const SizedBox(height: 20),
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
