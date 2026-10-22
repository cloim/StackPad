package com.cloimism.stackpad.widget;

import static org.junit.Assert.*;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.view.View;
import android.widget.FrameLayout;
import android.widget.RemoteViews;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import java.io.File;
import java.io.FileOutputStream;
import java.lang.reflect.Method;
import org.json.JSONArray;
import org.json.JSONObject;
import org.junit.Test;
import org.junit.runner.RunWith;

@RunWith(AndroidJUnit4.class)
public class UsageWidgetTest {
    @Test public void gaugesKeepExactFillAndWhiteDividers() {
        for (int count : new int[]{5, 7}) {
            Bitmap bitmap = UsageWidgetProvider.gauge(42.5, 0xFF779D82, count);
            assertEquals(0xFF779D82, bitmap.getPixel(5, 6));
            assertEquals(0xFFCBD3C3, bitmap.getPixel(270, 6));
            assertEquals(0xFF779D82, bitmap.getPixel(118, 6));
            assertEquals(0xFFCBD3C3, bitmap.getPixel(121, 6));
            for (int i = 1; i < count; i++) assertEquals(0xFFFFFFFF, bitmap.getPixel(Math.round(280f * i / count), 6));
        }
    }

    @Test public void remoteViewsRenderBothSizesAndErrorStates() throws Exception {
        Context context = InstrumentationRegistry.getInstrumentation().getTargetContext();
        WidgetStore store = new WidgetStore(context);
        // Test runs only on the disposable emulator and uses synthetic usage data.
        store.clear();
        store.connect("fixture", "fixture-token", "https://example.com");
        JSONArray providers = new JSONArray();
        String[] names = {"Claude", "Codex", "AG Gemini", "AG Claude/GPT"};
        for (int row = 0; row < names.length; row++) {
            JSONArray windows = new JSONArray();
            windows.put(new JSONObject().put("key", "five_hour").put("label", "5h").put("used_percent", 42.5 + row * 10));
            windows.put(new JSONObject().put("key", "weekly").put("label", "w").put("used_percent", 67 + row * 8));
            providers.put(new JSONObject().put("name", names[row]).put("status", "ok").put("windows", windows));
        }
        store.saveUsage(new JSONObject().put("providers", providers).toString(), System.currentTimeMillis());
        Method render = UsageWidgetProvider.class.getDeclaredMethod("render", Context.class, boolean.class);
        render.setAccessible(true);
        try {
            for (boolean detailed : new boolean[]{false, true}) {
                RemoteViews remote = (RemoteViews) render.invoke(null, context, detailed);
                InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> {
                    View view = remote.apply(context, new FrameLayout(context));
                    int width = Math.round(360 * context.getResources().getDisplayMetrics().density);
                    int height = Math.round((detailed ? 160 : 104) * context.getResources().getDisplayMetrics().density);
                    view.measure(View.MeasureSpec.makeMeasureSpec(width, View.MeasureSpec.EXACTLY), View.MeasureSpec.makeMeasureSpec(height, View.MeasureSpec.EXACTLY));
                    view.layout(0, 0, width, height);
                    Bitmap bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888);
                    view.draw(new Canvas(bitmap));
                    assertEquals(0xFFDFE5D9, bitmap.getPixel(width / 2, 3));
                    try (FileOutputStream output = new FileOutputStream(new File(context.getExternalFilesDir(null), "widget-" + (detailed ? "detailed" : "compact") + ".png"))) {
                        bitmap.compress(Bitmap.CompressFormat.PNG, 100, output);
                    } catch (Exception error) { throw new RuntimeException(error); }
                });
            }
            store.markRefreshing(true);
            RemoteViews refreshing = (RemoteViews) render.invoke(null, context, false);
            InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> {
                View view = refreshing.apply(context, new FrameLayout(context));
                assertEquals(View.VISIBLE, view.findViewById(com.cloimism.stackpad.R.id.loading).getVisibility());
            });
            store.markRefreshing(false);
            store.revoke("fixture-revoked");
            RemoteViews revoked = (RemoteViews) render.invoke(null, context, false);
            InstrumentationRegistry.getInstrumentation().runOnMainSync(() -> {
                View view = revoked.apply(context, new FrameLayout(context));
                assertEquals(View.VISIBLE, view.findViewById(com.cloimism.stackpad.R.id.empty).getVisibility());
                assertEquals(View.GONE, view.findViewById(com.cloimism.stackpad.R.id.rows).getVisibility());
            });
        } finally { store.clear(); }
    }
}
