import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../providers/translation_provider.dart';
import '../utils/app_theme.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

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
              Expanded(child: _Body()),
            ],
          ),
        ),
      ),
    );
  }
}

// ──────────────────────────────── Header ─────────────────────────────────────

class _Header extends StatelessWidget {
  @override
  Widget build(BuildContext context) => const Padding(
        padding: EdgeInsets.fromLTRB(20, 14, 20, 12),
        child: Text('Settings',
            style: TextStyle(
                color: Colors.white,
                fontSize: 20,
                fontWeight: FontWeight.bold)),
      );
}

// ──────────────────────────────── Body ───────────────────────────────────────

class _Body extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final p = context.watch<TranslationProvider>();

    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      children: [
        const _SectionLabel('Text-to-Speech'),
        _Card(children: [
          _SliderRow(
            icon: Icons.speed_rounded,
            title: 'Speech Rate',
            subtitle: 'Speed of spoken translations',
            value: p.ttsRate,
            min: 0.1,
            max: 1.0,
            divisions: 9,
            onChanged: p.setTtsRate,
          ),
          const _Sep(),
          _SliderRow(
            icon: Icons.graphic_eq_rounded,
            title: 'Pitch',
            subtitle: 'Voice pitch of TTS output',
            value: p.ttsPitch,
            min: 0.5,
            max: 2.0,
            divisions: 15,
            onChanged: p.setTtsPitch,
          ),
          const _Sep(),
          _SwitchRow(
            icon: Icons.volume_up_rounded,
            title: 'Auto-Speak',
            subtitle: 'Speak translation automatically',
            value: p.autoSpeak,
            onChanged: p.setAutoSpeak,
          ),
          const _Sep(),
          _TestTtsRow(),
        ]),
        const SizedBox(height: 22),
        const _SectionLabel('Server Connection'),
        _Card(children: [
          _ServerUrlRow(
            url: p.serverUrl,
            onSave: p.setServerUrl,
          ),
        ]),
        const SizedBox(height: 22),
        const _SectionLabel('Data'),
        _Card(children: [
          _ActionRow(
            icon: Icons.delete_sweep_rounded,
            iconColor: Colors.redAccent,
            title: 'Clear Translation History',
            subtitle: '${p.history.length} translations stored',
            onTap: () => _confirmClear(context, p),
          ),
        ]),
        const SizedBox(height: 22),
        const _SectionLabel('About'),
        const _Card(children: [
          _InfoRow(label: 'App', value: 'Smart Headphone App'),
          _Sep(),
          _InfoRow(label: 'Version', value: '1.0.0'),
          _Sep(),
          _InfoRow(label: 'Translation', value: 'Flask + deep-translator'),
          _Sep(),
          _InfoRow(label: 'Offline Engine', value: 'Argostranslate'),
          _Sep(),
          _InfoRow(label: 'Languages', value: '34 supported'),
          _Sep(),
          _InfoRow(label: 'Hardware', value: 'Raspberry Pi'),
        ]),
        const SizedBox(height: 32),
      ],
    );
  }

  void _confirmClear(BuildContext context, TranslationProvider p) {
    if (p.history.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('History is already empty'),
          backgroundColor: const Color(0xFF1A3050),
          behavior: SnackBarBehavior.floating,
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          margin: const EdgeInsets.all(16),
        ),
      );
      return;
    }
    showDialog(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: const Color(0xFF1A2D4E),
        shape:
            RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        title: const Text('Clear History',
            style: TextStyle(color: Colors.white)),
        content: const Text('Delete all saved translations?',
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
              p.clearHistory();
              Navigator.pop(context);
            },
            child: const Text('Delete'),
          ),
        ],
      ),
    );
  }
}

// ──────────────────────────── Shared Widgets ─────────────────────────────────

class _SectionLabel extends StatelessWidget {
  final String title;
  const _SectionLabel(this.title);

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.only(bottom: 10, top: 8),
        child: Text(title.toUpperCase(),
            style: const TextStyle(
                color: AppTheme.accent,
                fontSize: 11,
                fontWeight: FontWeight.bold,
                letterSpacing: 2.0)),
      );
}

class _Card extends StatelessWidget {
  final List<Widget> children;
  const _Card({required this.children});

  @override
  Widget build(BuildContext context) => Container(
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
        child: Column(children: children),
      );
}

class _Sep extends StatelessWidget {
  const _Sep();

  @override
  Widget build(BuildContext context) =>
      const Divider(color: Colors.white10, height: 1, indent: 52);
}

class _SliderRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final double value;
  final double min;
  final double max;
  final int divisions;
  final void Function(double) onChanged;

  const _SliderRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.min,
    required this.max,
    required this.divisions,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 14, 16, 4),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(7),
                  decoration: BoxDecoration(
                    color: AppTheme.accent.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(icon, color: AppTheme.accent, size: 18),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(title,
                          style: const TextStyle(
                              color: Colors.white, fontSize: 15)),
                      Text(subtitle,
                          style: const TextStyle(
                              color: Colors.white38, fontSize: 12)),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: AppTheme.accent.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(value.toStringAsFixed(1),
                      style: const TextStyle(
                          color: AppTheme.accent,
                          fontWeight: FontWeight.bold,
                          fontSize: 13)),
                ),
              ],
            ),
            Slider(
              value: value,
              min: min,
              max: max,
              divisions: divisions,
              onChanged: onChanged,
            ),
          ],
        ),
      );
}

class _SwitchRow extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final bool value;
  final void Function(bool) onChanged;

  const _SwitchRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(7),
              decoration: BoxDecoration(
                color: AppTheme.accent.withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Icon(icon, color: AppTheme.accent, size: 18),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(title,
                      style: const TextStyle(
                          color: Colors.white, fontSize: 15)),
                  Text(subtitle,
                      style: const TextStyle(
                          color: Colors.white38, fontSize: 12)),
                ],
              ),
            ),
            Switch(value: value, onChanged: onChanged),
          ],
        ),
      );
}

class _TestTtsRow extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    final p = context.read<TranslationProvider>();
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 14),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(7),
            decoration: BoxDecoration(
              color: AppTheme.accentGreen.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(8),
            ),
            child: const Icon(Icons.play_circle_outline_rounded,
                color: AppTheme.accentGreen, size: 18),
          ),
          const SizedBox(width: 12),
          const Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Test Speech',
                    style:
                        TextStyle(color: Colors.white, fontSize: 15)),
                Text('Preview current TTS settings',
                    style:
                        TextStyle(color: Colors.white38, fontSize: 12)),
              ],
            ),
          ),
          ElevatedButton(
            onPressed: p.testTts,
            style: ElevatedButton.styleFrom(
              backgroundColor: AppTheme.accentGreen.withValues(alpha: 0.15),
              foregroundColor: AppTheme.accentGreen,
              elevation: 0,
              shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                  side: BorderSide(
                      color: AppTheme.accentGreen.withValues(alpha: 0.4))),
              padding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            ),
            child: const Text('Test', style: TextStyle(fontSize: 13)),
          ),
        ],
      ),
    );
  }
}

class _ActionRow extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  const _ActionRow({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) => InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(18),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
          child: Row(
            children: [
              Container(
                padding: const EdgeInsets.all(7),
                decoration: BoxDecoration(
                  color: iconColor.withValues(alpha: 0.1),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Icon(icon, color: iconColor, size: 18),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title,
                        style: TextStyle(color: iconColor, fontSize: 15)),
                    Text(subtitle,
                        style: const TextStyle(
                            color: Colors.white38, fontSize: 12)),
                  ],
                ),
              ),
              Icon(Icons.chevron_right_rounded,
                  color: iconColor.withValues(alpha: 0.5), size: 20),
            ],
          ),
        ),
      );
}

class _ServerUrlRow extends StatefulWidget {
  final String url;
  final Future<void> Function(String) onSave;

  const _ServerUrlRow({required this.url, required this.onSave});

  @override
  State<_ServerUrlRow> createState() => _ServerUrlRowState();
}

class _ServerUrlRowState extends State<_ServerUrlRow> {
  late final TextEditingController _ctrl;
  bool _editing = false;

  @override
  void initState() {
    super.initState();
    _ctrl = TextEditingController(text: widget.url);
  }

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(7),
                  decoration: BoxDecoration(
                    color: AppTheme.accent.withValues(alpha: 0.1),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Icon(Icons.dns_rounded,
                      color: AppTheme.accent, size: 18),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Python Server URL',
                          style: TextStyle(color: Colors.white, fontSize: 15)),
                      Text('For offline mode & deepfake detection',
                          style:
                              TextStyle(color: Colors.white38, fontSize: 12)),
                    ],
                  ),
                ),
                GestureDetector(
                  onTap: () => setState(() => _editing = !_editing),
                  child: Icon(
                    _editing ? Icons.close_rounded : Icons.edit_rounded,
                    color: Colors.white38,
                    size: 18,
                  ),
                ),
              ],
            ),
            if (_editing) ...[
              const SizedBox(height: 10),
              TextField(
                controller: _ctrl,
                style: const TextStyle(color: Colors.white, fontSize: 13),
                decoration: InputDecoration(
                  hintText: 'http://192.168.x.x:5000',
                  hintStyle: const TextStyle(color: Colors.white24),
                  filled: true,
                  fillColor: Colors.white10,
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                  border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(10),
                      borderSide: BorderSide.none),
                  suffixIcon: TextButton(
                    onPressed: () {
                      widget.onSave(_ctrl.text.trim());
                      setState(() => _editing = false);
                    },
                    child: const Text('Save',
                        style: TextStyle(color: AppTheme.accent)),
                  ),
                ),
              ),
              const SizedBox(height: 6),
              const Text(
                  'Run: py main_controller.py  →  Select "Start Flask API"',
                  style:
                      TextStyle(color: Colors.white24, fontSize: 11)),
            ] else ...[
              const SizedBox(height: 6),
              Text(widget.url,
                  style: const TextStyle(
                      color: AppTheme.accent, fontSize: 12)),
            ],
          ],
        ),
      );
}

class _InfoRow extends StatelessWidget {
  final String label;
  final String value;
  const _InfoRow({required this.label, required this.value});

  @override
  Widget build(BuildContext context) => Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        child: Row(
          children: [
            Text(label,
                style: const TextStyle(color: Colors.white54, fontSize: 14)),
            const Spacer(),
            Text(value,
                style: const TextStyle(
                    color: AppTheme.accent,
                    fontSize: 14,
                    fontWeight: FontWeight.w500)),
          ],
        ),
      );
}
