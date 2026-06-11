import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'api_service.dart';

enum WhatsAppIntegrationState { loading, connected, disconnected, failedConnection }

class WhatsAppStateManager extends ChangeNotifier {
  final ApiService _apiService = ApiService();
  
  WhatsAppIntegrationState _state = WhatsAppIntegrationState.loading;
  String? _phoneNumber;
  String? _wabaId;
  String? _errorMessage;

  // Global Key constants for local cache survival checks
  static const String _cacheKey = 'cledger_waba_state_cache';

  WhatsAppStateManager() {
    initializeState();
  }

  WhatsAppIntegrationState get state => _state;
  String? get phoneNumber => _phoneNumber;
  String? get wabaId => _wabaId;
  String? get errorMessage => _errorMessage;
  bool get isConnected => _state == WhatsAppIntegrationState.connected;

  /// Loads locally cached parameters to instantly render status across restarts before sync ticks complete
  Future<void> initializeState() async {
    _state = WhatsAppIntegrationState.loading;
    notifyListeners();

    try {
      final prefs = await SharedPreferences.getInstance();
      final cachedData = prefs.getString(_cacheKey);

      if (cachedData != null) {
        final Map<String, dynamic> decoded = jsonDecode(cachedData);
        _phoneNumber = decoded['phone_number'];
        _wabaId = decoded['waba_id'];
        _state = decoded['is_connected'] == true 
            ? WhatsAppIntegrationState.connected 
            : WhatsAppIntegrationState.disconnected;
      } else {
        _state = WhatsAppIntegrationState.disconnected;
      }
    } catch (e) {
      _state = WhatsAppIntegrationState.disconnected;
    }
    notifyListeners();

    // Trigger an immediate background synchronization query to match the backend authority state
    syncWithBackend();
  }

  /// Queries backend authority mapping nodes to enforce tenant state alignment
  Future<void> syncWithBackend() async {
    try {
      final response = await _apiService.client.get('/api/v1/whatsapp/status');
      final bool connected = response.data['connected'] ?? false;
      
      if (connected) {
        _state = WhatsAppIntegrationState.connected;
        _phoneNumber = response.data['phone_number'];
        _wabaId = response.data['waba_id'];
        _errorMessage = null;
      } else {
        _state = WhatsAppIntegrationState.disconnected;
        _phoneNumber = null;
        _wabaId = null;
        _errorMessage = null;
      }
      
      await _persistToLocalCache();
    } on ApiException catch (e) {
      _errorMessage = e.message;
      // If a network connection error happens, keep the last known state rather than clearing it out
      if (_state != WhatsAppIntegrationState.connected) {
        _state = WhatsAppIntegrationState.failedConnection;
      }
    } catch (e) {
      _errorMessage = 'Synchronization cycle dropped: $e';
      if (_state != WhatsAppIntegrationState.connected) {
        _state = WhatsAppIntegrationState.failedConnection;
      }
    } finally {
      notifyListeners();
    }
  }

  /// Triggers a state disconnection pipeline and purges cached values
  Future<void> disconnectChannel() async {
    _state = WhatsAppIntegrationState.loading;
    notifyListeners();

    try {
      await _apiService.client.post('/api/v1/whatsapp/disconnect');
      _state = WhatsAppIntegrationState.disconnected;
      _phoneNumber = null;
      _wabaId = null;
      _errorMessage = null;
      
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove(_cacheKey);
    } on ApiException catch (e) {
      _errorMessage = e.message;
      _state = WhatsAppIntegrationState.connected; // Rollback to active state on execution fault
    } catch (e) {
      _errorMessage = 'Disconnection request failed: $e';
      _state = WhatsAppIntegrationState.connected;
    } finally {
      notifyListeners();
    }
  }

  /// Private helper utility to commit runtime definitions into device flash storage block fields
  Future<void> _persistToLocalCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final cacheString = jsonEncode({
        'is_connected': _state == WhatsAppIntegrationState.connected,
        'phone_number': _phoneNumber,
        'waba_id': _wabaId,
      });
      await prefs.setString(_cacheKey, cacheString);
    } catch (e) {
      // Storage access tracking block warnings can be passed down safely to diagnostic monitors
    }
  }
}
