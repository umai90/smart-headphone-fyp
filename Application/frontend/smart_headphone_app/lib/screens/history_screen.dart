import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../models/translation_entry.dart';
import '../providers/translation_provider.dart';
import '../utils/app_theme.dart';

class HistoryScreen extends StatelessWidget {
  const HistoryScreen({super.key});

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
              _Header(),
              Expanded(child: _HistoryList()),
            ],
          ),
        ),
      ),
    );
  }
}

// ─────────────────────────────── Header ──────────────────────────────────────

class _Header extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final p = context.watch<TranslationProvider>();
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 14, 20, 12),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('History',
                    style: TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.bold)),
                if (p.history.isNotEmpty)
                  Text('${p.history.length} translations',
                      style: const TextStyle(
                          color: Colors.white38, fontSize: 12)),
              ],
            ),
          ),
          if (p.history.isNotEmpty)
            TextButton.icon(
              onPressed: () => _confirmClear(context),
              icon: const Icon(Icons.delete_sweep_rounded,
                  size: 16, color: Colors.redAccent),
              label: const Text('Clear',
                  style: TextStyle(color: Colors.redAccent, fontSize: 13)),
            ),
        ],
      ),
    );
  }

  void _confirmClear(BuildContext context) {
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: const Color(0xFF1A2D4E),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        title: const Text('Clear All History',
            style: TextStyle(color: Colors.white)),
        content: const Text('This will permanently delete all translations.',
            style: TextStyle(color: Colors.white60)),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel',
                  style: TextStyle(color: Colors.white54))),
          ElevatedButton(
            style: ElevatedButton.styleFrom(
                backgroundColor: Colors.redAccent,
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(10))),
            onPressed: () {
              context.read<TranslationProvider>().clearHistory();
              Navigator.pop(context);
            },
            child: const Text('Delete All'),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────── History List ────────────────────────────────────

class _HistoryList extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final p = context.watch<TranslationProvider>();

    if (p.history.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(28),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: Colors.white.withValues(alpha: 0.03),
                border:
                    Border.all(color: Colors.white.withValues(alpha: 0.06)),
              ),
              child: const Icon(Icons.history_rounded,
                  color: Colors.white10, size: 64),
            ),
            const SizedBox(height: 20),
            const Text('No translations yet',
                style: TextStyle(color: Colors.white38, fontSize: 17)),
            const SizedBox(height: 8),
            const Text('Your history will appear here',
                style: TextStyle(color: Colors.white24, fontSize: 13)),
          ],
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.fromLTRB(20, 4, 20, 24),
      itemCount: p.history.length,
      itemBuilder: (ctx, i) {
        final entry = p.history[i];
        return Dismissible(
          key: Key(entry.id),
          direction: DismissDirection.endToStart,
          onDismissed: (_) {
            HapticFeedback.lightImpact();
            ctx.read<TranslationProvider>().removeEntry(entry.id);
          },
          background: Container(
            margin: const EdgeInsets.only(bottom: 12),
            decoration: BoxDecoration(
              color: Colors.redAccent.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(18),
              border: Border.all(
                  color: Colors.redAccent.withValues(alpha: 0.3)),
            ),
            alignment: Alignment.centerRight,
            padding: const EdgeInsets.only(right: 20),
            child: const Icon(Icons.delete_rounded,
                color: Colors.redAccent, size: 24),
          ),
          child: _EntryCard(entry: entry),
        );
      },
    );
  }
}

// ─────────────────────────── Entry Card ──────────────────────────────────────

class _EntryCard extends StatelessWidget {
  final TranslationEntry entry;
  const _EntryCard({required this.entry});

  Color _scoreColor(double s) {
    if (s >= 0.8) return AppTheme.accentGreen;
    if (s >= 0.5) return Colors.amber;
    return Colors.redAccent;
  }

  @override
  Widget build(BuildContext context) {
    final p = context.read<TranslationProvider>();
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF14253D), Color(0xFF1C3050)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
        boxShadow: [
          BoxShadow(
              color: Colors.black.withValues(alpha: 0.25),
              blurRadius: 12,
              offset: const Offset(0, 4))
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Header row
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 0),
            child: Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppTheme.accent.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(
                        color: AppTheme.accent.withValues(alpha: 0.25)),
                  ),
                  child: Text(
                    '${entry.fromFlag} ${entry.fromLanguage}  →  ${entry.toFlag} ${entry.toLanguage}',
                    style: const TextStyle(
                        color: AppTheme.accent,
                        fontSize: 11,
                        fontWeight: FontWeight.w600),
                  ),
                ),
                const Spacer(),
                if (entry.matchScore > 0)
                  Container(
                    margin: const EdgeInsets.only(right: 8),
                    padding: const EdgeInsets.symmetric(
                        horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: _scoreColor(entry.matchScore)
                          .withValues(alpha: 0.12),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      '${(entry.matchScore * 100).toInt()}%',
                      style: TextStyle(
                          color: _scoreColor(entry.matchScore),
                          fontSize: 10,
                          fontWeight: FontWeight.bold),
                    ),
                  ),
                Text(_timeAgo(entry.timestamp),
                    style: const TextStyle(
                        color: Colors.white30, fontSize: 10)),
              ],
            ),
          ),
          // Original text
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 10, 14, 0),
            child: Text(entry.originalText,
                style: const TextStyle(
                    color: Colors.white54, fontSize: 13, height: 1.4)),
          ),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 14),
            child: Divider(color: Colors.white10, height: 18),
          ),
          // Translated text + actions
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 0, 12, 12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(entry.translatedText,
                      style: const TextStyle(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w500,
                          height: 1.5)),
                ),
                const SizedBox(width: 10),
                Column(
                  children: [
                    _SmallBtn(
                      icon: Icons.volume_up_rounded,
                      color: AppTheme.accentGreen,
                      tooltip: 'Speak translation',
                      onTap: () {
                        HapticFeedback.selectionClick();
                        p.speakEntry(entry);
                      },
                    ),
                    const SizedBox(height: 6),
                    _SmallBtn(
                      icon: Icons.copy_rounded,
                      color: Colors.white38,
                      tooltip: 'Copy',
                      onTap: () async {
                        HapticFeedback.selectionClick();
                        await p.copyToClipboard(entry.translatedText);
                        if (context.mounted) {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: const Text('Copied!',
                                  style: TextStyle(color: Colors.white)),
                              backgroundColor: const Color(0xFF1A3050),
                              duration: const Duration(seconds: 1),
                              behavior: SnackBarBehavior.floating,
                              shape: RoundedRectangleBorder(
                                  borderRadius: BorderRadius.circular(10)),
                              margin: const EdgeInsets.all(16),
                            ),
                          );
                        }
                      },
                    ),
                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _timeAgo(DateTime dt) {
    final diff = DateTime.now().difference(dt);
    if (diff.inSeconds < 60) return 'Just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    return '${dt.day}/${dt.month}/${dt.year}';
  }
}

class _SmallBtn extends StatelessWidget {
  final IconData icon;
  final Color color;
  final String tooltip;
  final VoidCallback onTap;

  const _SmallBtn(
      {required this.icon,
      required this.color,
      required this.tooltip,
      required this.onTap});

  @override
  Widget build(BuildContext context) => GestureDetector(
        onTap: onTap,
        child: Tooltip(
          message: tooltip,
          child: Container(
            padding: const EdgeInsets.all(7),
            decoration: BoxDecoration(
              color: color.withValues(alpha: 0.12),
              borderRadius: BorderRadius.circular(8),
              border:
                  Border.all(color: color.withValues(alpha: 0.2)),
            ),
            child: Icon(icon, color: color, size: 17),
          ),
        ),
      );
}
