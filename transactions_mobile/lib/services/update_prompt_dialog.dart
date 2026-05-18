import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/update_metadata.dart';

class UpdatePromptDialog extends StatefulWidget {
  final UpdateMetadata metadata;
  final String currentVersionDisplay;
  final bool isForced;

  const UpdatePromptDialog({
    super.key,
    required this.metadata,
    required this.currentVersionDisplay,
    required this.isForced,
  });

  @override
  State<UpdatePromptDialog> createState() => _UpdatePromptDialogState();
}

class _UpdatePromptDialogState extends State<UpdatePromptDialog> {
  bool _isLaunching = false;

  Future<void> _launchDownloadUrl() async {
    if (_isLaunching) return;

    setState(() {
      _isLaunching = true;
    });

    final uri = Uri.tryParse(widget.metadata.downloadUrl);

    if (uri == null || uri.scheme != 'https') {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Error: Invalid or insecure (non-HTTPS) download URL.'),
            backgroundColor: Colors.redAccent,
          ),
        );
        setState(() {
          _isLaunching = false;
        });
      }
      return;
    }

    if (await canLaunchUrl(uri)) {
      try {
        await launchUrl(
          uri,
          mode: LaunchMode.externalApplication,
        );
        if (mounted) {
          _showInstallGuidance(context);
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Download launch failed: $e'),
              backgroundColor: Colors.redAccent,
            ),
          );
        }
      }
    } else {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('No supported application found to open URL: ${widget.metadata.downloadUrl}'),
            backgroundColor: Colors.redAccent,
          ),
        );
      }
    }

    if (mounted) {
      setState(() {
        _isLaunching = false;
      });
    }
  }

  void _showInstallGuidance(BuildContext context) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      isDismissible: !widget.isForced,
      enableDrag: !widget.isForced,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (bottomSheetContext) {
        return PopScope(
          canPop: !widget.isForced,
          child: Padding(
            padding: const EdgeInsets.all(24.0),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Icon(Icons.security, size: 48, color: Theme.of(context).colorScheme.primary),
                const SizedBox(height: 16),
                Text(
                  'Installation Instructions',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 24),
                _buildGuidanceStep(
                  context,
                  '1',
                  'Wait for download',
                  'Check your notification panel or Downloads folder for the APK file.',
                ),
                const SizedBox(height: 16),
                _buildGuidanceStep(
                  context,
                  '2',
                  'Open the file',
                  'Tap the completed download to initiate the update.',
                ),
                const SizedBox(height: 16),
                _buildGuidanceStep(
                  context,
                  '3',
                  'Allow Permissions',
                  'If blocked, tap "Settings" and enable "Allow from this source" (Install Unknown Apps).',
                ),
                const SizedBox(height: 16),
                _buildGuidanceStep(
                  context,
                  '4',
                  'Install',
                  'Select "Install" or "Update" on the prompt and wait for completion.',
                ),
                const SizedBox(height: 24),
                ElevatedButton(
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Theme.of(context).colorScheme.primary,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(vertical: 12.0),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(8.0),
                    ),
                  ),
                  onPressed: () {
                    if (!widget.isForced) {
                      Navigator.of(bottomSheetContext).pop();
                      Navigator.of(context).pop();
                    }
                  },
                  child: Text(
                    widget.isForced ? 'Waiting for Installation...' : 'Got it',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildGuidanceStep(BuildContext context, String number, String title, String description) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        CircleAvatar(
          radius: 14,
          backgroundColor: Theme.of(context).colorScheme.primary.withOpacity(0.1),
          foregroundColor: Theme.of(context).colorScheme.primary,
          child: Text(number, style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
              const SizedBox(height: 4),
              Text(
                description,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(height: 1.3),
              ),
            ],
          ),
        )
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    // Prevent dismissal via system back gesture if the update is mandatory
    return PopScope(
      canPop: !widget.isForced,
      child: Dialog(
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16.0),
        ),
        backgroundColor: Theme.of(context).colorScheme.surface,
        elevation: 4.0,
        child: Padding(
          padding: const EdgeInsets.all(20.0),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Header Icon
              Container(
                padding: const EdgeInsets.all(12.0),
                decoration: BoxDecoration(
                  color: Theme.of(context).colorScheme.primary.withOpacity(0.1),
                  shape: BoxShape.circle,
                ),
                child: Icon(
                  widget.isForced ? Icons.system_update_alt : Icons.update,
                  size: 36,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
              const SizedBox(height: 16),

              // Title
              Text(
                widget.isForced ? 'Critical Update Required' : 'Update Available',
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: Theme.of(context).colorScheme.onSurface,
                    ),
              ),
              const SizedBox(height: 12),

              // Version Diff Comparison
              Container(
                padding: const EdgeInsets.symmetric(vertical: 8.0, horizontal: 12.0),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(8.0),
                  border: Border.all(color: Colors.grey.shade300),
                ),
                child: Column(
                  children: [
                    _VersionRow(
                      label: 'Installed Version:',
                      value: widget.currentVersionDisplay,
                      isOld: true,
                    ),
                    const SizedBox(height: 4),
                    _VersionRow(
                      label: 'Latest Version:',
                      value: 'v${widget.metadata.latestVersion} (Build ${widget.metadata.buildNumber})',
                      isOld: false,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              // Release Notes Section
              if (widget.metadata.releaseNotes.isNotEmpty) ...[
                Text(
                  'What\'s New:',
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                ),
                const SizedBox(height: 6),
                ConstrainedBox(
                  constraints: const BoxConstraints(maxHeight: 120),
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: widget.metadata.releaseNotes
                          .map((note) => Padding(
                                padding: const EdgeInsets.only(bottom: 4.0),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const Text('• ', style: TextStyle(fontWeight: FontWeight.bold)),
                                    Expanded(
                                      child: Text(
                                        note,
                                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                              height: 1.3,
                                            ),
                                      ),
                                    ),
                                  ],
                                ),
                              ))
                          .toList(),
                    ),
                  ),
                ),
                const SizedBox(height: 20),
              ],

              // Actions
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.primary,
                  foregroundColor: Colors.white,
                  disabledBackgroundColor: Theme.of(context).colorScheme.primary.withOpacity(0.6),
                  disabledForegroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 12.0),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8.0),
                  ),
                ),
                onPressed: _isLaunching ? null : _launchDownloadUrl,
                child: _isLaunching
                    ? const Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          SizedBox(
                            height: 16,
                            width: 16,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              color: Colors.white,
                            ),
                          ),
                          SizedBox(width: 8),
                          Text(
                            'Opening download...',
                            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                          ),
                        ],
                      )
                    : const Text(
                        'Update Now',
                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                      ),
              ),
              
              // Only render Dismiss button if update is optional
              if (!widget.isForced) ...[
                const SizedBox(height: 8),
                TextButton(
                  style: TextButton.styleFrom(
                    foregroundColor: Colors.grey.shade600,
                  ),
                  onPressed: _isLaunching ? null : () => Navigator.of(context).pop(),
                  child: const Text('Dismiss'),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _VersionRow extends StatelessWidget {
  final String label;
  final String value;
  final bool isOld;

  const _VersionRow({
    required this.label,
    required this.value,
    required this.isOld,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(
          label,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                color: Colors.grey.shade600,
              ),
        ),
        Text(
          value,
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                fontWeight: FontWeight.bold,
                color: isOld ? Colors.grey.shade500 : Theme.of(context).colorScheme.onSurface,
              ),
        ),
      ],
    );
  }
}
