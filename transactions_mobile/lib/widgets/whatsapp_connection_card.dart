import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';
import '../services/whatsapp_state_manager.dart';
import '../services/api_service.dart';

class WhatsAppConnectionCard extends StatefulWidget {
  const WhatsAppConnectionCard({super.key});

  @override
  State<WhatsAppConnectionCard> createState() => _WhatsAppConnectionCardState();
}

class _WhatsAppConnectionCardState extends State<WhatsAppConnectionCard> {
  late final WhatsAppStateManager _stateManager;

  @override
  void initState() {
    super.initState();
    _stateManager = WhatsAppStateManager();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _stateManager,
      builder: (context, _) {
        if (_stateManager.state == WhatsAppIntegrationState.loading) {
          return Card(
            elevation: 1.5,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12.0)),
            child: const Padding(
              padding: EdgeInsets.all(24.0),
              child: Center(
                child: CircularProgressIndicator(
                  valueColor: AlwaysStoppedAnimation<Color>(Color(0xFF0F9D88)),
                ),
              ),
            ),
          );
        }

        final bool hasError = _stateManager.errorMessage != null;
        final bool isConnected = _stateManager.isConnected;

        return Card(
          elevation: 1.5,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12.0)),
          child: Padding(
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(8.0),
                          decoration: BoxDecoration(
                            color: isConnected 
                                ? Colors.green.withOpacity(0.1) 
                                : (hasError ? Colors.red.withOpacity(0.1) : Colors.orange.withOpacity(0.1)),
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            isConnected ? Icons.chat_bubble : (hasError ? Icons.error_outline : Icons.link_off), 
                            color: isConnected ? Colors.green : (hasError ? Colors.redAccent : Colors.orange),
                            size: 24,
                          ),
                        ),
                        const SizedBox(width: 12),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text(
                              'WhatsApp Integration',
                              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                            ),
                            const SizedBox(height: 2),
                            Row(
                              children: [
                                Container(
                                  width: 8,
                                  height: 8,
                                  decoration: BoxDecoration(
                                    color: isConnected ? Colors.green : (hasError ? Colors.redAccent : Colors.orange),
                                    shape: BoxShape.circle,
                                  ),
                                ),
                                const SizedBox(width: 6),
                                Text(
                                  isConnected 
                                      ? 'Connected Status Verified' 
                                      : (hasError ? 'Sync Interrupted' : 'Action Required'),
                                  style: TextStyle(
                                    fontSize: 13, 
                                    color: isConnected ? Colors.green : (hasError ? Colors.redAccent : Colors.orange),
                                    fontWeight: FontWeight.w500,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ],
                    ),
                    IconButton(
                      icon: const Icon(Icons.sync, color: Colors.grey, size: 20),
                      onPressed: () => _stateManager.syncWithBackend(),
                      tooltip: 'Re-sync Status Now',
                    ),
                  ],
                ),
                const Divider(height: 24),
                
                if (hasError) ...[
                  Container(
                    padding: const EdgeInsets.all(10.0),
                    margin: const EdgeInsets.only(bottom: 12.0),
                    decoration: BoxDecoration(
                      color: Colors.redAccent.withOpacity(0.05),
                      borderRadius: BorderRadius.circular(8.0),
                      border: Border.all(color: Colors.redAccent.withOpacity(0.15)),
                    ),
                    child: Text(
                      _stateManager.errorMessage!,
                      style: const TextStyle(color: Colors.redAccent, fontSize: 13),
                    ),
                  ),
                ],

                if (isConnected) ...[
                  _buildStatusRow(Icons.phone, 'Phone Number', _stateManager.phoneNumber ?? 'Not resolved'),
                  const SizedBox(height: 8),
                  _buildStatusRow(Icons.badge, 'WABA Account ID', _stateManager.wabaId ?? 'Not resolved'),
                  const Divider(height: 24),
                  Align(
                    alignment: Alignment.centerRight,
                    child: TextButton.icon(
                      onPressed: () => _showDisconnectWarning(context),
                      icon: const Icon(Icons.link_off, size: 16, color: Colors.redAccent),
                      label: const Text(
                        'Disconnect Channel',
                        style: TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w600),
                      ),
                    ),
                  ),
                ] else ...[
                  const Text(
                    'WhatsApp connection setup must be securely launched and verified using the browser context on your Admin Portal dashboard.',
                    style: TextStyle(fontSize: 13, height: 1.4, color: Colors.grey),
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF0F9D88),
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 12, horizontal: 16),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    onPressed: _launchMetaOnboardingPortal,
                    icon: const Icon(Icons.open_in_new, size: 18),
                    label: const Text(
                      'Launch Meta Setup Wizard',
                      style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Container(
                    padding: const EdgeInsets.all(10.0),
                    decoration: BoxDecoration(
                      color: Colors.grey.withOpacity(0.05),
                      borderRadius: BorderRadius.circular(8.0),
                      border: Border.all(color: Colors.grey.withOpacity(0.15)),
                    ),
                    child: Row(
                      children: [
                        const Icon(Icons.info, size: 16, color: Color(0xFF0F9D88)),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'Status will auto-update here once link actions complete.',
                            style: TextStyle(fontSize: 12, color: Colors.grey[700], fontStyle: FontStyle.italic),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
      },
    );
  }

  Future<void> _launchMetaOnboardingPortal() async {
    try {
      // Extract the configured target base URL string from the active ApiService configuration network tier
      final String configuredBaseUrl = ApiService().client.options.baseUrl;
      
      // Points directly to the exposed static layout template handler served by the FastAPI engine
      final Uri targetPortalUri = Uri.parse('$configuredBaseUrl/api/v1/whatsapp/setup-surface');
      
      if (await canLaunchUrl(targetPortalUri)) {
        await launchUrl(
          targetPortalUri,
          mode: LaunchMode.externalApplication, // Forces launch via default system browser container
        );
      } else {
        _stateManager.syncWithBackend(); // Force sync retry evaluation if execution limits trip
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not trigger authorization container: $e')),
      );
    }
  }

  void _showDisconnectWarning(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Disconnect WhatsApp?'),
        content: const Text(
          'This will detach your WABA channel identity mappings from this tenant database layout context. Webhooks will drop operational paths immediately.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel', style: TextStyle(color: Colors.grey)),
          ),
          ElevatedButton(
            style: ElevatedButton.styleFrom(backgroundColor: Colors.redAccent),
            onPressed: () {
              Navigator.pop(context);
              _stateManager.disconnectChannel();
            },
            child: const Text('Disconnect Identity', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
  }

  Widget _buildStatusRow(IconData icon, String label, String value) {
    return Row(
      children: [
        Icon(icon, size: 16, color: Colors.grey[600]),
        const SizedBox(width: 8),
        Text(
          '$label: ',
          style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w500, color: Colors.grey),
        ),
        Expanded(
          child: Text(
            value,
            style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600, color: Colors.black87),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }
}
