package android.widget;

import android.database.DataSetObserver;
import android.view.View;
import android.view.ViewGroup;

import java.util.ArrayList;
import java.util.List;

public abstract class BaseAdapter implements ListAdapter {

    private final List<DataSetObserver> observers = new ArrayList<>();

    @Override
    public boolean hasStableIds() { return false; }

    @Override
    public int getItemViewType(int position) { return 0; }

    @Override
    public int getViewTypeCount() { return 1; }

    @Override
    public boolean isEmpty() { return getCount() == 0; }

    @Override
    public boolean areAllItemsEnabled() { return true; }

    @Override
    public boolean isEnabled(int position) { return true; }

    @Override
    public void registerDataSetObserver(DataSetObserver observer) {
        if (observer != null) observers.add(observer);
    }

    @Override
    public void unregisterDataSetObserver(DataSetObserver observer) {
        observers.remove(observer);
    }

    public void notifyDataSetChanged() {
        for (DataSetObserver observer : new ArrayList<>(observers)) observer.onChanged();
    }

    public void notifyDataSetInvalidated() {
        for (DataSetObserver observer : new ArrayList<>(observers)) observer.onInvalidated();
    }

    @Override
    public View getView(int position, View convertView, ViewGroup parent) { return convertView; }
}
