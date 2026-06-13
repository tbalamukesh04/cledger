import 'package:flutter/material.dart';
import 'package:package_info_plus/package_info_plus.dart';
import '../widgets/loading_state.dart';
import '../widgets/whatsapp_connection_card.dart';

class SettingsScreen extends StatefulWidget {
  final Future<void> Function() onRefreshRequested;

  const SettingsScreen({
    super.key,
    required this.onRefreshRequested,
  });

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  String _versionString = "Loading...";
  bool _isRefreshing = false;

  @override
  void initState() {
    super.initState();
    _loadPackageInfo();
  }

  Future<void> _loadPackageInfo() async {
    try {
      final info = await PackageInfo.fromPlatform();
      if (mounted) {
        setState(() {
          _versionString = "v${info.version} (Build ${info.buildNumber})";
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _versionString = "v1.0.0 (Build 1)";
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
        elevation: 0,
      ),
      body: ListView(
        padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 20.0),
        children: [
          const _SettingsSectionHeader(title: 'Application Controls'),
          _SettingsCardTile(
            icon: Icons.sync,
            title: 'Manual Refresh',
            subtitle: 'Trigger background synchronization',
            trailing: _isRefreshing
                ? const CustomLoadingState.inline()
                : const Icon(Icons.chevron_right, color: Colors.grey),
            onTap: _isRefreshing
                ? null
                : () async {
                    setState(() {
                      _isRefreshing = true;
                    });
                    try {
                      await widget.onRefreshRequested();
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('Transactions synchronized successfully.'),
                          ),
                        );
                      }
                    } catch (e) {
                      if (mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text('Synchronization failed: $e'),
                          ),
                        );
                      }
                    } finally {
                      if (mounted) {
                        setState(() {
                          _isRefreshing = false;
                        });
                      }
                    }
                  },
          ),
          const SizedBox(height: 28),
          const _SettingsSectionHeader(title: 'Business Integration'),
          WhatsAppConnectionCard(),
          const SizedBox(height: 28),
          const _SettingsSectionHeader(title: 'About'),
          _SettingsCardTile(
            icon: Icons.info_outline,
            title: 'App Version',
            trailing: Text(
              _versionString,
              style: const TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w600,
                color: Colors.grey,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SettingsSectionHeader extends StatelessWidget {
  final String title;

  const _SettingsSectionHeader({required this.title});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, bottom: 10.0),
      child: Text(
        title.toUpperCase(),
        style: const TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.bold,
          letterSpacing: 1.2,
          color: Color(0xFF0F9D88), // Day 79 Brand Primary Alignment
        ),
      ),
    );
  }
}

class _SettingsCardTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String? subtitle;
  final Widget? trailing;
  final VoidCallback? onTap;

  const _SettingsCardTile({
    required this.icon,
    required this.title,
    this.subtitle,
    this.trailing,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 1.5,
      margin: const EdgeInsets.only(bottom: 12.0),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12.0),
      ),
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 4.0),
        leading: Container(
          padding: const EdgeInsets.all(8.0),
          decoration: BoxDecoration(
            color: const Color(0xFF0F9D88).withOpacity(0.1),
            shape: BoxShape.circle,
          ),
          child: Icon(icon, color: const Color(0xFF0F9D88), size: 22),
        ),
        title: Text(
          title,
          style: const TextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w500,
          ),
        ),
        subtitle: subtitle != null
            ? Text(
                subtitle!,
                style: Theme.of(context).textTheme.bodySmall,
              )
            : null,
        trailing: trailing,
        onTap: onTap,
      ),
    );
  }
}