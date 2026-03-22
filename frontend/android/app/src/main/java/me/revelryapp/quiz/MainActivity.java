package me.revelryapp.quiz;

import android.webkit.WebSettings;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onResume() {
        super.onResume();
        // Allow mixed content (HTTPS page loading HTTP resources)
        // Needed for local dev where Capacitor uses https:// but backend is http://
        // In production, API is also HTTPS so this is a no-op
        if (getBridge() != null && getBridge().getWebView() != null) {
            getBridge().getWebView().getSettings()
                .setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }
    }
}
