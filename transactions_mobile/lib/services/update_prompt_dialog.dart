import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../models/update_metadata.dart';

class UpdatePromptDialog extends StatelessWidget {
  final UpdateMetadata metadata;
  final String currentVersionDisplay;
  final bool isForced;

  const UpdatePromptDialog({
    super.key,
    required this.metadata,
    required this.currentVersionDisplay,
    required this.isForced,
  });

  Future<void> _launchDownloadUrl(BuildContext context) async {
    final uri = Uri.tryParse(metadata.downloadUrl);
    if (uri != null && await canLaunchUrl(uri)) {
      await launchUrl(
        uri,
        mode: LaunchMode.externalApplication, // Delegates to external browser safely
      );
    } else {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Could not launch update URL: ${metadata.downloadUrl}'),
            backgroundColor: Colors.redAccent,
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // Prevent dismissal via system back gesture if the update is mandatory
    return PopScope(
      canPop: !isForced,
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
                  isForced ? Icons.system_update_alt : Icons.update,
                  size: 36,
                  color: Theme.of(context).colorScheme.primary,
                ),
              ),
              const SizedBox(height: 16),

              // Title
              Text(
                isForced ? 'Critical Update Required' : 'Update Available',
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
                      value: currentVersionDisplay,
                      isOld: true,
                    ),
                    const SizedBox(height: 4),
                    _VersionRow(
                      label: 'Latest Version:',
                      value: 'v${metadata.latestVersion} (Build ${metadata.buildNumber})',
                      isOld: false,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              // Release Notes Section
              if (metadata.releaseNotes.isNotEmpty) ...[
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
                      children: metadata.releaseNotes
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
                  padding: const EdgeInsets.symmetric(vertical: 12.0),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8.0),
                  ),
                ),
                onPressed: () => _launchDownloadUrl(context),
                child: const Text(
                  'Update Now',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                ),
              ),
              
              // Only render Dismiss button if update is optional
              if (!isForced) ...[
                const SizedBox(height: 8),
                TextButton(
                  style: TextButton.styleFrom(
                    foregroundColor: Colors.grey.shade600,
                  ),
                  onPressed: () => Navigator.of(context).pop(),
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
